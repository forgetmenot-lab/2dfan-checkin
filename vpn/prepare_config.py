"""Prepare the supplied inline OpenVPN profile without printing its secrets."""
import argparse
import ipaddress
from pathlib import Path
import shlex
import socket


def convert(content, resolve):
    output = []
    block = None
    remotes = 0
    for line in content.replace("\r\n", "\n").splitlines():
        stripped = line.strip()
        if block:
            output.append(line)
            if stripped == f"</{block}>":
                block = None
            continue
        if stripped.startswith("<") and stripped.endswith(">"):
            name = stripped[1:-1]
            if name not in {"ca", "cert", "key", "tls-auth", "tls-crypt"}:
                raise ValueError("Unsupported inline block")
            block = name
            output.append(line)
            continue
        if not stripped or stripped.startswith(("#", ";")):
            output.append(line)
            continue
        fields = shlex.split(stripped, comments=True)
        option = fields[0]
        if option in {"up", "down", "route-up", "route-pre-down", "ipchange", "plugin", "tls-verify", "config", "management"}:
            raise ValueError("External scripts/configuration are unsupported")
        if option in {"ca", "cert", "key", "tls-auth", "tls-crypt"}:
            raise ValueError("Use a profile with embedded certificates and keys")
        if option == "route-method":
            continue
        if option == "remote":
            remotes += 1
            if len(fields) not in {3, 4}:
                raise ValueError("Expected remote host port [protocol]")
            address = resolve(fields[1])
            if ipaddress.ip_address(address).version != 4:
                raise ValueError("IPv4 endpoint required")
            fields[1] = address
            line = " ".join(fields)
        output.append(line)
    if block or remotes != 1:
        raise ValueError("Expected one remote and complete inline blocks")
    return "\n".join(output) + "\n"


def resolve_ipv4(host):
    return socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM)[0][4][0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    prepared = convert(args.source.read_text(encoding="utf-8-sig"), resolve_ipv4)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(prepared, encoding="utf-8", newline="\n")
    args.destination.chmod(0o600)
    print("VPN profile prepared; embedded keys preserved; endpoint resolved to IPv4.")
