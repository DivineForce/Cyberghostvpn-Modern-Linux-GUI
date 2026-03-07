#!/bin/bash

set -e

if [ "$UID" -ne 0 ]; then
    echo "Please run the installer with sudo!"
    exit 1
fi

echo -e "\nCyberGhost Installer ...\n"

apt update

requiredPackages=(curl openvpn resolvconf wireguard-tools)

for package in "${requiredPackages[@]}"; do
    echo -n "Check if \"$package\" package is already installed ... "

    if command -v "$package" >/dev/null 2>&1 || dpkg -s "$package" >/dev/null 2>&1; then
        echo "Yes"
    else
        echo "No, installing ..."
        apt install -y "$package"
        echo "Done."
    fi
done

echo "Continue ..."

if [ -d /usr/local/cyberghost ]; then
    rm -rf /usr/local/cyberghost
fi

echo "Installing application ..."
mkdir -p /usr/local/cyberghost

if [ ! -d cyberghost ]; then
    echo "Expected ./cyberghost directory was not found."
    echo "Run this installer from the extracted CyberGhost CLI replacement package."
    exit 1
fi

cp -r ./cyberghost/* /usr/local/cyberghost
chmod -R 755 /usr/local/cyberghost

echo "Create symlinks ..."

if [ -L /usr/bin/cyberghostvpn ]; then
    rm -f /usr/bin/cyberghostvpn
fi

ln -sf /usr/local/cyberghost/cyberghostvpn /usr/bin/cyberghostvpn

cyberghostvpn --setup
