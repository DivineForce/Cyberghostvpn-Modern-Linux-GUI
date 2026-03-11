# CyberGhost Modern Client

![Python](https://img.shields.io/badge/Python-3.x-blue)
![Platform](https://img.shields.io/badge/Platform-Linux-green)
![VPN](https://img.shields.io/badge/VPN-OpenVPN-orange)
![Status](https://img.shields.io/badge/Status-Active-success)

CyberGhost Modern is a Linux desktop UI for connecting to CyberGhost OpenVPN endpoints.

It provides:
- a PySide6 (Qt) GUI for country/city/server selection
- profile + settings persistence
- direct `openvpn` process launch
- server discovery through `cyberghostvpn` CLI parsing

## Screenshots
![screenshot](/screenshots/Screenshot1.png)

## Credits

This project is inspired by community work:

- Ifleg - CyberGhost CLI fix: https://github.com/ifleg/cyberghost
- Picharly - CyberGhost GUI: https://github.com/picharly/cyberghostvpn-gui
- CyberGhost VPN infrastructure: https://www.cyberghostvpn.com/

## What It Actually Does

Connection path:
1. Reads credentials from `~/.cyberghost/config.ini` (or token file fallback)
2. Builds and launches an `openvpn` command directly
3. Streams OpenVPN logs into the GUI and updates status

Discovery path:
1. Uses `cyberghostvpn` CLI output for countries, cities, and server instances
2. Caches these results in `~/.cyberghost/server_cache.json`

UI features:
- Country -> City -> Server flow
- Quick connect
- Command preview
- Live log panel
- Public IP lookup
- Country flags (downloaded and cached)
- Recent server list
- Profiles (save/apply/delete)
- Settings persistence
- Uptime and tunnel traffic display

## Current Limitations

- Only OpenVPN is actually used for connection
- "Service" and "Server Type" selectors are present, but custom engine support is OpenVPN only
- Kill switch option exists in settings but is currently not implemented as firewall enforcement
- Requires Linux networking permissions for tunnel creation

## Requirements

System packages:

```bash
sudo apt update
sudo apt install openvpn resolvconf python3 python3-pip curl iproute2
```

Python packages:

```bash
python3 -m pip install -r requirements.txt
```

Current Python dependencies:
- `Pillow`
- `PySide6`

## Runtime Dependencies

The app expects these binaries in PATH unless overridden:

- `openvpn` (or `OPENVPN_BIN` env var)
- `cyberghostvpn` (or `CYBERGHOST_BIN` env var)

Example override:

```bash
export OPENVPN_BIN=/usr/sbin/openvpn
export CYBERGHOST_BIN=/usr/bin/cyberghostvpn
```

## Project Structure

```text
cyberghost_modern_v12/
|- app.py
|- README.md
|- requirements.txt
|- cyberghostvpnCLI_install_shell_replacement.sh
`- cyberghost_gui/
   |- app.py
   |- ui.py
   |- service.py
   |- cyberghost_cli.py
   |- openvpn_runner.py
   |- status_parser.py
   |- credentials.py
   |- store.py
   |- config.py
   |- models.py
   |- assets.py
   `- helpers.py
```

## Configuration

User data is stored under:

```text
~/.cyberghost/
```

Create credentials file:

```text
~/.cyberghost/config.ini
```

Example:

```ini
[device]
token=YOUR_DEVICE_TOKEN
secret=YOUR_DEVICE_SECRET
```

Fallback token file format:

```text
token=YOUR_DEVICE_TOKEN
secret=YOUR_DEVICE_SECRET
```

## Certificates

OpenVPN certs are expected at:

```text
/usr/local/cyberghost/certs/openvpn/
```

Required files:

```text
ca.crt
client.crt
client.key
```

Recommended permissions:

```bash
sudo chmod 600 /usr/local/cyberghost/certs/openvpn/client.key
sudo chmod 644 /usr/local/cyberghost/certs/openvpn/client.crt
sudo chmod 644 /usr/local/cyberghost/certs/openvpn/ca.crt
```

## OpenVPN Permissions (Important)

OpenVPN needs permission to create tunnel interfaces:

```bash
sudo setcap CAP_NET_ADMIN=ep /usr/sbin/openvpn
```

Verify:

```bash
getcap /usr/sbin/openvpn
```

Expected output:

```text
/usr/sbin/openvpn cap_net_admin=ep
```

## Running the App

```bash
python3 app.py
```

## Manual Verification Checklist

After launching:
1. Confirm countries load without CLI errors
2. Select country/city/server and click Connect
3. Wait for "Connected" status and OpenVPN success logs
4. Use "Check IP" and verify location/IP changed
5. Click Stop and verify status returns to ready

Extra verification:

```bash
curl ifconfig.me
ip -s link show tun0
```

## Troubleshooting

`OpenVPN binary not found`:
- install OpenVPN or set `OPENVPN_BIN`

`CyberGhost CLI binary was not found`:
- install CyberGhost CLI replacement or set `CYBERGHOST_BIN`

`Tunnel permission missing` / `operation not permitted`:
- apply `setcap` command above
- ensure `/dev/net/tun` exists

No countries/cities/servers:
- run CLI manually to check output:

```bash
cyberghostvpn --country-code
```

## Security Notes

- Never share `~/.cyberghost/config.ini`
- Protect private keys and credential files
- Do not expose token/secret in logs/screenshots

## License

This project is released under the MIT License.

## Disclaimer

This project is not affiliated with CyberGhost VPN.
