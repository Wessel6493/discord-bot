$ips = Get-Content "C:\Users\wesse\discord-bot\uptimerobot_ips.txt"

foreach ($ip in $ips) {
    New-NetFirewallRule -DisplayName "Allow UptimeRobot $ip" -Direction Inbound -RemoteAddress $ip -Action Allow
}