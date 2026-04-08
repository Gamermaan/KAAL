#ifndef PROTOCOL_H
#define PROTOCOL_H

#define PROTOCOL_VERSION "1.0"

// Message Type Macros
#define MSG_REGISTER "register"
#define MSG_HEARTBEAT "heartbeat"
#define MSG_RESULT "result"
#define MSG_ACK "ack"
#define MSG_STATUS "status"
#define MSG_CHUNK "chunk"
#define MSG_SHELL_OUTPUT "shell_output"
#define MSG_LOG "log"
#define MSG_COMMAND "command"
#define MSG_CONTROL "control"
#define MSG_CONFIG "config"
#define MSG_STREAM_DATA "stream_data"
#define MSG_STREAM_END "stream_end"

typedef struct {
  int ack_required;
  int priority;
  int retry;
  int control;
  int ttl;
  const char *compression;
  const char *encryption;
} protocol_flags_t;

#endif // PROTOCOL_H
