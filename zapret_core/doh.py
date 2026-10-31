# doh.py — управление DNS over HTTPS (DoH) в Windows
import base64
import json
import subprocess
import winreg

from .misc import decode_output, is_admin

DOH_PROVIDERS = {
    "cloudflare": {
        "name": "Cloudflare",
        "ipv4": ["1.1.1.1", "1.0.0.1"],
        "ipv6": ["2606:4700:4700::1111", "2606:4700:4700::1001"],
        "template": "https://cloudflare-dns.com/dns-query",
        "description": "Быстрый глобальный DoH (1.1.1.1)",
    },
    "google": {
        "name": "Google DNS",
        "ipv4": ["8.8.8.8", "8.8.4.4"],
        "ipv6": ["2001:4860:4860::8888", "2001:4860:4860::8844"],
        "template": "https://dns.google/dns-query",
        "description": "Надёжный Google Public DNS (8.8.8.8)",
    },
    "quad9": {
        "name": "Quad9",
        "ipv4": ["9.9.9.9", "149.112.112.112"],
        "ipv6": ["2620:fe::fe", "2620:fe::9"],
        "template": "https://dns.quad9.net/dns-query",
        "description": "Приватный Quad9 без логирования (9.9.9.9)",
    },
    "adguard": {
        "name": "AdGuard DNS",
        "ipv4": ["94.140.14.14", "94.140.15.15"],
        "ipv6": ["2a10:50c0::ad1:ff", "2a10:50c0::ad2:ff"],
        "template": "https://dns.adguard-dns.com/dns-query",
        "description": "Фильтрация рекламы и трекеров (94.140.14.14)",
    },
}


def _run_cmd(cmd: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, creationflags=0x08000000, timeout=20)
        out = decode_output(r.stdout) + decode_output(r.stderr)
        return r.returncode == 0, out.strip()
    except Exception as e:
        return False, str(e)


def _run_ps_script(script: str) -> tuple[bool, str]:
    """Безопасный вызов PowerShell через -EncodedCommand (UTF-16LE в Base64).
    Исключает проблемы с экранированием кавычек, кириллицей и спецсимволами."""
    try:
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        return _run_cmd(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded])
    except Exception as e:
        return False, str(e)


def _get_active_adapter_names() -> list[str]:
    """Список псевдонимов активных сетевых адаптеров."""
    script = "(Get-NetAdapter | Where-Object Status -eq 'Up').InterfaceAlias"
    ok, out = _run_ps_script(script)
    if ok and out:
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    return ["Ethernet"]


def get_doh_status() -> dict:
    """Определение текущего статуса DoH на активных интерфейсах Windows."""
    adapters = _get_active_adapter_names()
    if not adapters:
        return {
            "ok": True,
            "enabled": False,
            "provider": "disabled",
            "provider_name": "Нет активных адаптеров",
            "servers": [],
            "adapters": [],
            "autodoh": False,
        }

    first_ad_json = json.dumps(adapters[0])
    ps_cmd = f"$ad = {first_ad_json}; (Get-DnsClientServerAddress -InterfaceAlias $ad -AddressFamily IPv4).ServerAddresses -join ','"
    ok, dns_out = _run_ps_script(ps_cmd)
    servers = [s.strip() for s in dns_out.split(",") if s.strip()] if ok else []

    # Check EnableAutoDoh in registry
    autodoh = False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters") as k:
            val, _ = winreg.QueryValueEx(k, "EnableAutoDoh")
            autodoh = (val in (1, 2))
    except Exception:
        autodoh = False

    # Match servers to provider
    detected_provider = "disabled"
    provider_name = "Отключен (DHCP)"
    if servers:
        for key, info in DOH_PROVIDERS.items():
            if any(s in info["ipv4"] for s in servers):
                detected_provider = key
                provider_name = f"{info['name']} ({servers[0]})"
                break
        else:
            detected_provider = "custom"
            provider_name = f"Кастомный ({', '.join(servers)})"

    enabled = detected_provider != "disabled"
    return {
        "ok": True,
        "enabled": enabled,
        "provider": detected_provider,
        "provider_name": provider_name,
        "servers": servers,
        "adapters": adapters,
        "autodoh": autodoh,
    }


def set_doh(provider_key: str) -> dict:
    """Включение DoH для выбранного провайдера на всех активных адаптерах (IPv4 + IPv6)."""
    if not is_admin():
        return {"ok": False, "error": "Для настройки DoH требуются права администратора (UAC)."}

    provider = DOH_PROVIDERS.get(provider_key.lower())
    if not provider:
        return {"ok": False, "error": f"Неизвестный провайдер DoH: {provider_key}"}

    adapters = _get_active_adapter_names()
    ipv4_servers = list(provider["ipv4"])
    ipv6_servers = list(provider.get("ipv6", []))
    all_servers = list(ipv4_servers) + list(ipv6_servers)
    template = provider["template"]

    # 1. Задаем DNS адреса для каждого активного адаптера через безопасный PowerShell
    srv_json = json.dumps(all_servers)
    errors = []
    success_count = 0
    for ad in adapters:
        ad_json = json.dumps(ad)
        ps = f"$ad = {ad_json}; $srv = {srv_json}; Set-DnsClientServerAddress -InterfaceAlias $ad -ServerAddresses $srv"
        ok, err = _run_ps_script(ps)
        if ok:
            success_count += 1
        else:
            errors.append(f"{ad}: {err}")

    if success_count == 0 and errors:
        return {"ok": False, "error": f"Не удалось применить DNS: {'; '.join(errors)}"}

    # 2. Настраиваем шаблоны шифрования в Windows DoH (netsh dns add encryption для IPv4 и IPv6)
    for srv in all_servers:
        _run_cmd(["netsh", "dns", "add", "encryption", f"server={srv}",
                  f"dohtemplate={template}", "autoupgrade=yes", "udpfallback=yes"])

    # 3. Включаем глобальный флаг EnableAutoDoh = 2 (принудительный / авто DoH) в реестре
    try:
        with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters") as k:
            winreg.SetValueEx(k, "EnableAutoDoh", 0, winreg.REG_DWORD, 2)
    except OSError as e:
        return {"ok": False, "error": f"Ошибка реестра EnableAutoDoh: {e}"}

    # 4. Сброс кэша DNS
    _run_cmd(["ipconfig", "/flushdns"])

    return {
        "ok": True,
        "provider": provider_key,
        "provider_name": provider["name"],
        "message": f"DoH ({provider['name']}) успешно настроен для интерфейсов: {', '.join(adapters)} (IPv4 + IPv6).",
    }


def disable_doh() -> dict:
    """Сброс DNS на получение по DHCP (автоматически) и отключение DoH."""
    if not is_admin():
        return {"ok": False, "error": "Для сброса DoH требуются права администратора (UAC)."}

    adapters = _get_active_adapter_names()
    for ad in adapters:
        ad_json = json.dumps(ad)
        ps = f"$ad = {ad_json}; Set-DnsClientServerAddress -InterfaceAlias $ad -ResetServerAddresses"
        _run_ps_script(ps)

    # Сбрасываем флаг реестра
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, "EnableAutoDoh")
    except Exception:
        pass

    _run_cmd(["ipconfig", "/flushdns"])
    return {
        "ok": True,
        "message": f"DoH отключен. Для интерфейсов ({', '.join(adapters)}) восстановлено получение DNS по DHCP.",
    }
