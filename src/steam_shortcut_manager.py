#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import sys
import struct
import binascii
import zlib
import vdf
from pathlib import Path
try:
    from PIL import Image, ImageDraw, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARN: Pillow (PIL) library not found. Artwork processing will be skipped.", file=sys.stderr)

def find_steam_userdata_path():
    home = Path.home()
    steam_paths_to_check = [
        home / ".steam/root/userdata",
        home / ".local/share/Steam/userdata",
        home / ".steam/steam/userdata",
        home / ".var/app/com.valvesoftware.Steam/data/Steam/userdata"
    ]
    candidate_user_dirs = []
    for steam_base_path in steam_paths_to_check:
        if steam_base_path.is_dir():
            for user_id_dir in steam_base_path.iterdir():
                if user_id_dir.is_dir() and user_id_dir.name.isdigit():
                    localconfig_vdf = user_id_dir / "config" / "localconfig.vdf"
                    if localconfig_vdf.is_file():
                        try:
                            mtime = localconfig_vdf.stat().st_mtime
                            candidate_user_dirs.append({'path': user_id_dir, 'mtime': mtime, 'steam_base': steam_base_path, 'user_id_str': user_id_dir.name})
                        except OSError: pass
    if not candidate_user_dirs: return None
    candidate_user_dirs.sort(key=lambda x: x['mtime'], reverse=True)
    latest_login_timestamp = 0
    active_user_dir_from_login = None
    for candidate in candidate_user_dirs:
        loginusers_path = candidate['steam_base'].parent / "config/loginusers.vdf"
        user_id_str_candidate = candidate['user_id_str']
        try:
            if loginusers_path.is_file():
                with open(loginusers_path, 'r', encoding='utf-8') as f:
                    login_users_data = vdf.load(f)
                user_details = login_users_data.get('users', {}).get(user_id_str_candidate)
                if user_details and isinstance(user_details, dict):
                    timestamp = int(user_details.get('Timestamp', 0))
                    if timestamp > latest_login_timestamp:
                        latest_login_timestamp = timestamp
                        active_user_dir_from_login = candidate['path']
        except Exception as e:
            print(f"WARN: Could not process loginusers.vdf for user {user_id_str_candidate}: {e}", file=sys.stderr)
    if active_user_dir_from_login:
        print(f"INFO: Active Steam user directory found via loginusers.vdf: {active_user_dir_from_login}")
        return active_user_dir_from_login
    elif candidate_user_dirs:
        fallback_user_dir = candidate_user_dirs[0]['path']
        print(f"INFO: Using fallback Steam user directory (latest localconfig.vdf): {fallback_user_dir}")
        return fallback_user_dir
    return None

_crc32_tab_manual = []
def _init_crc32_tab_manual():
    global _crc32_tab_manual
    if _crc32_tab_manual: return
    _crc32_tab_manual = [0] * 256
    for i in range(256):
        crc = i
        for _ in range(8): crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
        _crc32_tab_manual[i] = crc
_init_crc32_tab_manual()

def _calculate_crc32_for_steam_id(text_to_hash: str) -> int:
    return zlib.crc32(text_to_hash.encode('utf-8'))

def generate_preliminary_64bit_id(exe_path_for_hash: str, app_name_for_hash: str) -> int:
    string_to_hash = exe_path_for_hash + app_name_for_hash
    crc = _calculate_crc32_for_steam_id(string_to_hash)
    top_32_bits = crc | 0x80000000
    full_64_bit_id = (top_32_bits << 32) | 0x02000000
    return full_64_bit_id

def generate_short_appid_for_artwork(exe_path_cleaned: str, app_name_cleaned: str) -> str:
    exe_path_quoted_for_hash = f'"{exe_path_cleaned}"'
    prelim_id = generate_preliminary_64bit_id(exe_path_quoted_for_hash, app_name_cleaned)
    short_id = prelim_id >> 32
    return str(short_id)

def generate_appid_for_vdf_entry(exe_path_cleaned: str, app_name_cleaned: str) -> int:
    exe_path_quoted_for_hash = f'"{exe_path_cleaned}"'
    prelim_id = generate_preliminary_64bit_id(exe_path_quoted_for_hash, app_name_cleaned)
    short_id_val = prelim_id >> 32
    vdf_entry_appid = short_id_val - 0x100000000
    return int(vdf_entry_appid)

TARGET_SIZES = {
    "library_header_capsule": (920, 430),
    "portrait": (600, 900),
    "hero": (1920, 620),
    "icon_square": (512, 512),
    "logo_steam": (640, 360)
}

GRADIENT_COLOR_START = (40, 40, 60)
GRADIENT_COLOR_END = (20, 20, 30)

APP_LOGO_SCALE_FACTOR_LANDSCAPE = 0.75
APP_LOGO_SCALE_FACTOR_PORTRAIT = 0.8
APP_LOGO_SCALE_FACTOR_ICON = 0.8

def create_gradient_image(width: int, height: int, color_start_rgb: tuple, color_end_rgb: tuple, direction="vertical") -> Image.Image:
    base = Image.new("RGB", (width, height), color_start_rgb)
    draw = ImageDraw.Draw(base)
    if direction == "vertical":
        for y in range(height):
            blend = y / float(height)
            r = int(color_start_rgb[0] * (1 - blend) + color_end_rgb[0] * blend)
            g = int(color_start_rgb[1] * (1 - blend) + color_end_rgb[1] * blend)
            b = int(color_start_rgb[2] * (1 - blend) + color_end_rgb[2] * blend)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
    elif direction == "horizontal":
        for x in range(width):
            blend = x / float(width)
            r = int(color_start_rgb[0] * (1 - blend) + color_end_rgb[0] * blend)
            g = int(color_start_rgb[1] * (1 - blend) + color_end_rgb[1] * blend)
            b = int(color_start_rgb[2] * (1 - blend) + color_end_rgb[2] * blend)
            draw.line([(x, 0), (x, height)], fill=(r, g, b))
    return base

def scale_image_to_fit_bbox(image: Image.Image, bbox_width: int, bbox_height: int, resample_method) -> Image.Image:
    original_width, original_height = image.size
    if original_width == 0 or original_height == 0: return image.copy()
    width_ratio = float(bbox_width) / original_width
    height_ratio = float(bbox_height) / original_height
    scale_ratio = min(width_ratio, height_ratio)
    new_width = max(1, int(original_width * scale_ratio))
    new_height = max(1, int(original_height * scale_ratio))
    return image.resize((new_width, new_height), resample_method)

def save_steam_artwork(
    artwork_short_appid_str: str,
    app_logo_source_path_str: str,
    grid_dir: Path,
    deckstore_logo_path_str: str = None
):
    if not PIL_AVAILABLE:
        print("WARN: Pillow library not available. Artwork processing skipped.", file=sys.stderr)
        return False

    app_logo_source_path = Path(app_logo_source_path_str)
    if not grid_dir or not app_logo_source_path.is_file():
        print(f"ERROR: Invalid app logo source path or grid directory. AppLogo='{app_logo_source_path}', Grid='{grid_dir}'", file=sys.stderr)
        return False

    try:
        grid_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"ERROR: Could not create grid directory: {grid_dir} - {e}", file=sys.stderr)
        return False

    try:
        app_logo_original = Image.open(app_logo_source_path).convert("RGBA")
        ds_logo_original = None
        if deckstore_logo_path_str and Path(deckstore_logo_path_str).is_file():
            ds_logo_original = Image.open(deckstore_logo_path_str).convert("RGBA")
        elif deckstore_logo_path_str:
            print(f"WARN: DeckStore logo not found at '{deckstore_logo_path_str}', skipping DeckStore branding.")

        base_name = artwork_short_appid_str

        header_capsule_target_size = TARGET_SIZES["library_header_capsule"]
        header_canvas = create_gradient_image(header_capsule_target_size[0], header_capsule_target_size[1], GRADIENT_COLOR_START, GRADIENT_COLOR_END, direction="horizontal")

        header_app_logo_bbox_h = int(header_capsule_target_size[1] * APP_LOGO_SCALE_FACTOR_LANDSCAPE)
        header_app_logo_bbox_w = int(header_capsule_target_size[0] * 0.9)

        app_logo_for_header = scale_image_to_fit_bbox(app_logo_original.copy(), header_app_logo_bbox_w, header_app_logo_bbox_h, Image.Resampling.LANCZOS)

        header_logo_x = (header_capsule_target_size[0] - app_logo_for_header.width) // 2
        header_logo_y = (header_capsule_target_size[1] - app_logo_for_header.height) // 2
        header_canvas.paste(app_logo_for_header, (header_logo_x, header_logo_y), app_logo_for_header)

        if ds_logo_original:
            ds_logo_for_header = ds_logo_original.copy()
            ds_logo_header_height = int(header_capsule_target_size[1] * 0.15)
            ds_logo_for_header = scale_image_to_fit_bbox(ds_logo_for_header, int(ds_logo_header_height * (ds_logo_for_header.width / float(ds_logo_for_header.height)) if ds_logo_for_header.height > 0 else ds_logo_header_height), ds_logo_header_height, Image.Resampling.LANCZOS)
            header_canvas.paste(ds_logo_for_header, (20, header_capsule_target_size[1] - ds_logo_for_header.height - 20), ds_logo_for_header)

        header_path_png = grid_dir / f"{base_name}.png"
        header_canvas.save(header_path_png, "PNG"); print(f"INFO: Enhanced Library Header Capsule saved: {header_path_png}")

        hero_target_size = TARGET_SIZES["hero"]
        hero_canvas = create_gradient_image(hero_target_size[0], hero_target_size[1], GRADIENT_COLOR_START, GRADIENT_COLOR_END, direction="horizontal")

        hero_app_logo_bbox_h = int(hero_target_size[1] * APP_LOGO_SCALE_FACTOR_LANDSCAPE)
        hero_app_logo_bbox_w = int(hero_target_size[0] * 0.7)

        app_logo_for_hero = scale_image_to_fit_bbox(app_logo_original.copy(), hero_app_logo_bbox_w, hero_app_logo_bbox_h, Image.Resampling.LANCZOS)

        hero_logo_x = (hero_target_size[0] - app_logo_for_hero.width) // 2
        hero_logo_y = (hero_target_size[1] - app_logo_for_hero.height) // 2
        hero_canvas.paste(app_logo_for_hero, (hero_logo_x, hero_logo_y), app_logo_for_hero)

        if ds_logo_original:
            ds_logo_for_hero = ds_logo_original.copy()
            ds_logo_hero_height = int(hero_target_size[1] * 0.1)
            ds_logo_for_hero = scale_image_to_fit_bbox(ds_logo_for_hero, int(ds_logo_hero_height * (ds_logo_for_hero.width / float(ds_logo_for_hero.height)) if ds_logo_for_hero.height > 0 else ds_logo_hero_height), ds_logo_hero_height , Image.Resampling.LANCZOS)
            hero_canvas.paste(ds_logo_for_hero, (30, 30), ds_logo_for_hero)

        hero_path_png = grid_dir / f"{base_name}_hero.png"
        hero_canvas.save(hero_path_png, "PNG"); print(f"INFO: Enhanced Hero image saved: {hero_path_png}")

        portrait_target_size = TARGET_SIZES["portrait"]
        portrait_canvas = create_gradient_image(portrait_target_size[0], portrait_target_size[1], GRADIENT_COLOR_START, GRADIENT_COLOR_END, direction="vertical")

        portrait_app_logo_bbox_w = int(portrait_target_size[0] * APP_LOGO_SCALE_FACTOR_PORTRAIT)
        portrait_app_logo_bbox_h = int(portrait_target_size[1] * APP_LOGO_SCALE_FACTOR_PORTRAIT)

        app_logo_for_portrait = scale_image_to_fit_bbox(app_logo_original.copy(), portrait_app_logo_bbox_w, portrait_app_logo_bbox_h, Image.Resampling.LANCZOS)

        portrait_logo_x = (portrait_target_size[0] - app_logo_for_portrait.width) // 2
        portrait_logo_y = (portrait_target_size[1] - app_logo_for_portrait.height) // 2
        portrait_canvas.paste(app_logo_for_portrait, (portrait_logo_x, portrait_logo_y), app_logo_for_portrait)

        if ds_logo_original:
            ds_logo_for_portrait = ds_logo_original.copy()
            ds_logo_portrait_width = int(portrait_target_size[0] * 0.15)
            ds_logo_for_portrait = scale_image_to_fit_bbox(ds_logo_for_portrait, ds_logo_portrait_width, int(ds_logo_portrait_width * (ds_logo_for_portrait.height / float(ds_logo_for_portrait.width)) if ds_logo_for_portrait.width > 0 else ds_logo_portrait_width), Image.Resampling.LANCZOS)
            portrait_canvas.paste(ds_logo_for_portrait, (20, 20), ds_logo_for_portrait)

        grid_path_p_png = grid_dir / f"{base_name}p.png"
        portrait_canvas.save(grid_path_p_png, "PNG"); print(f"INFO: Enhanced Portrait (p) image saved: {grid_path_p_png}")

        icon_target_size = TARGET_SIZES["icon_square"]
        icon_canvas = Image.new("RGBA", icon_target_size, (0,0,0,0))

        icon_app_logo_bbox_w = int(icon_target_size[0] * APP_LOGO_SCALE_FACTOR_ICON)
        icon_app_logo_bbox_h = int(icon_target_size[1] * APP_LOGO_SCALE_FACTOR_ICON)

        app_logo_for_icon = scale_image_to_fit_bbox(app_logo_original.copy(), icon_app_logo_bbox_w, icon_app_logo_bbox_h, Image.Resampling.LANCZOS)

        icon_logo_x = (icon_target_size[0] - app_logo_for_icon.width) // 2
        icon_logo_y = (icon_target_size[1] - app_logo_for_icon.height) // 2
        icon_canvas.paste(app_logo_for_icon, (icon_logo_x, icon_logo_y), app_logo_for_icon)

        icon_specific_png = grid_dir / f"{base_name}_icon.png"
        icon_canvas.save(icon_specific_png, "PNG"); print(f"INFO: Enhanced Icon image saved: {icon_specific_png}")

        logo_target_bbox_w, logo_target_bbox_h = TARGET_SIZES["logo_steam"]

        app_logo_for_steamlogo = scale_image_to_fit_bbox(app_logo_original.copy(), logo_target_bbox_w, logo_target_bbox_h, Image.Resampling.LANCZOS)

        final_steam_logo = Image.new("RGBA", app_logo_for_steamlogo.size, (0,0,0,0))
        final_steam_logo.paste(app_logo_for_steamlogo, (0,0), app_logo_for_steamlogo)

        logo_path_png = grid_dir / f"{base_name}_logo.png"
        final_steam_logo.save(logo_path_png, "PNG"); print(f"INFO: Enhanced Steam Logo image saved: {logo_path_png}")

        return True

    except FileNotFoundError:
        print(f"ERROR: App logo source file not found: {app_logo_source_path}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: Artwork processing failed for {app_logo_source_path}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False

def add_shortcut(
    userdata_path: Path,
    flatpak_appid_tag: str,
    app_name_param: str,
    exe_param: str,
    launch_options_param: str,
    icon_source_param: str,
    deckstore_logo_param: str = None
):
    shortcuts_path = userdata_path / "config/shortcuts.vdf"
    grid_path = userdata_path / "config/grid"

    shortcuts = {}
    original_vdf_data_structure = {}
    try:
        if shortcuts_path.is_file():
             with open(shortcuts_path, 'rb') as f:
                 original_vdf_data_structure = vdf.binary_load(f)
                 shortcuts = original_vdf_data_structure.get('shortcuts', original_vdf_data_structure)
             if not isinstance(shortcuts, dict): shortcuts = {}
        else:
            print(f"INFO: {shortcuts_path} does not exist, creating new.")
            shortcuts_path.parent.mkdir(parents=True, exist_ok=True)
            shortcuts = {}
            original_vdf_data_structure = {'shortcuts': shortcuts}

    except Exception as e:
        print(f"ERROR: Failed reading {shortcuts_path}: {e}", file=sys.stderr)
        shortcuts = {}
        original_vdf_data_structure = {'shortcuts': shortcuts}

    next_id = 0
    numeric_keys = sorted([int(k) for k in shortcuts.keys() if k.isdigit()])
    if numeric_keys:
        next_id = numeric_keys[-1] + 1
    shortcut_key_str = str(next_id)

    tag_to_find = f'DeckStore_{flatpak_appid_tag}'
    for key, entry_dict in shortcuts.items():
         if isinstance(entry_dict, dict) and tag_to_find in entry_dict.get('tags', {}).values():
             print(f"WARN: Shortcut für Flatpak AppID '{flatpak_appid_tag}' (Tag: '{tag_to_find}') scheint bereits zu existieren (Index: {key}). Überspringe das Hinzufügen.")
             return True

    clean_exe_for_id_gen = exe_param.strip('"')
    clean_name_for_id_gen = app_name_param.strip('"')

    artwork_short_id_str = generate_short_appid_for_artwork(clean_exe_for_id_gen, clean_name_for_id_gen)
    print(f"INFO: Generierte Short AppID für Artwork: {artwork_short_id_str}")
    vdf_entry_appid_int = generate_appid_for_vdf_entry(clean_exe_for_id_gen, clean_name_for_id_gen)
    print(f"INFO: Generierte 'appid' für VDF-Eintrag: {vdf_entry_appid_int}")

    icon_path_in_vdf = ""
    if icon_source_param:
        icon_path_in_vdf = str(grid_path / f"{artwork_short_id_str}_icon.png")

    shortcut_entry = {
        'appid': vdf_entry_appid_int,
        'AppName': app_name_param,
        'Exe': exe_param,
        'StartDir': os.path.dirname(exe_param) if os.path.isabs(exe_param) else ".",
        'icon': icon_path_in_vdf,
        'ShortcutPath': '',
        'LaunchOptions': launch_options_param,
        'IsHidden': 0, 'AllowDesktopConfig': 1, 'AllowOverlay': 1, 'OpenVR': 0,
        'Devkit': 0, 'DevkitGameID': '', 'DevkitOverrideAppID': 0,
        'LastPlayTime': 0,
        'FlatpakAppID': flatpak_appid_tag,
        'tags': {'0': tag_to_find }
    }
    if not os.path.isabs(exe_param) and shortcut_entry['StartDir'] == ".":
         print(f"WARN: Exe path '{exe_param}' ist nicht absolut. StartDir wird auf '.' gesetzt.")

    shortcuts[shortcut_key_str] = shortcut_entry
    print(f"INFO: Shortcut-Eintrag mit Index {shortcut_key_str} erstellt.")

    if 'shortcuts' in original_vdf_data_structure or not shortcuts_path.is_file():
        data_to_write_back = {'shortcuts': shortcuts}
    else:
        data_to_write_back = shortcuts

    try:
        with open(shortcuts_path, 'wb') as f:
            vdf.binary_dump(data_to_write_back, f)
        print(f"INFO: Erfolgreich in {shortcuts_path} geschrieben.")
    except Exception as e:
        print(f"ERROR: Fehler beim Schreiben von {shortcuts_path}: {e}", file=sys.stderr)
        return False

    if icon_source_param:
        if not save_steam_artwork(artwork_short_id_str, icon_source_param, grid_path, deckstore_logo_param):
           print(f"WARN: Fehler beim Speichern des Artworks, aber Shortcut wurde hinzugefügt.", file=sys.stderr)

    return True

def remove_shortcut(userdata_path: Path, flatpak_appid_tag_to_remove: str):
    shortcuts_path = userdata_path / "config/shortcuts.vdf"
    grid_path = userdata_path / "config/grid"
    print(f"INFO: Entferne Shortcut für Flatpak AppID Tag: {flatpak_appid_tag_to_remove}")
    if not shortcuts_path.is_file(): return True

    current_shortcuts = {}
    original_vdf_structure = {}
    try:
        with open(shortcuts_path, 'rb') as f:
            original_vdf_structure = vdf.binary_load(f)
            current_shortcuts = original_vdf_structure.get('shortcuts', original_vdf_structure)
            if not isinstance(current_shortcuts, dict): current_shortcuts = {}
    except Exception as e: return False

    shortcut_key_to_delete = None
    shortcut_entry_to_delete = None
    tag_to_find_for_removal = f'DeckStore_{flatpak_appid_tag_to_remove}'

    for key, entry_dict in list(current_shortcuts.items()):
        if isinstance(entry_dict, dict) and tag_to_find_for_removal in entry_dict.get('tags', {}).values():
            shortcut_key_to_delete = key
            shortcut_entry_to_delete = entry_dict
            break

    if shortcut_key_to_delete and shortcut_entry_to_delete:
        exe_for_artwork_id = shortcut_entry_to_delete.get('Exe', '').strip('"')
        name_for_artwork_id = shortcut_entry_to_delete.get('AppName', '').strip('"')
        del current_shortcuts[shortcut_key_to_delete]

        if 'shortcuts' in original_vdf_structure: data_to_write_back_after_delete = {'shortcuts': current_shortcuts}
        else: data_to_write_back_after_delete = current_shortcuts

        try:
            with open(shortcuts_path, 'wb') as f: vdf.binary_dump(data_to_write_back_after_delete, f)
        except Exception as e: return False

        if exe_for_artwork_id and name_for_artwork_id:
            try:
                artwork_appid_str_to_delete = generate_short_appid_for_artwork(exe_for_artwork_id, name_for_artwork_id)
                art_patterns_to_delete = [
                    f"{artwork_appid_str_to_delete}.png", f"{artwork_appid_str_to_delete}.jpg",
                    f"{artwork_appid_str_to_delete}p.png", f"{artwork_appid_str_to_delete}p.jpg",
                    f"{artwork_appid_str_to_delete}_hero.png", f"{artwork_appid_str_to_delete}_hero.jpg",
                    f"{artwork_appid_str_to_delete}_icon.png", f"{artwork_appid_str_to_delete}_icon.jpg",
                    f"{artwork_appid_str_to_delete}_logo.png", f"{artwork_appid_str_to_delete}_logo.jpg"
                ]
                for pattern in art_patterns_to_delete:
                    art_path = grid_path / pattern
                    if art_path.is_file(): art_path.unlink()
            except Exception as e_art: print(f"WARN: Fehler beim Löschen von Artwork: {e_art}", file=sys.stderr)
        return True
    else: return True

def check_shortcut(userdata_path: Path, flatpak_appid_tag_to_check: str):
    shortcuts_path = userdata_path / "config/shortcuts.vdf"
    if not shortcuts_path.is_file(): return False
    shortcuts = {}
    try:
        with open(shortcuts_path, 'rb') as f:
            loaded_data = vdf.binary_load(f)
            shortcuts = loaded_data.get('shortcuts', loaded_data)
            if not isinstance(shortcuts, dict): shortcuts = {}
    except Exception as e: return False
    tag_to_find_for_check = f'DeckStore_{flatpak_appid_tag_to_check}'
    for entry_dict in shortcuts.values():
        if isinstance(entry_dict, dict) and tag_to_find_for_check in entry_dict.get('tags', {}).values():
            return True
    return False

if __name__ == "__main__":
    _init_crc32_tab_manual()

    parser = argparse.ArgumentParser(description="Manage Steam non-game shortcuts with enhanced artwork generation.")
    parser.add_argument('--action', choices=['add', 'remove', 'check'], required=True, help="Aktion.")
    parser.add_argument('--appid_tag', required=True, help="Eindeutiger Tag für die App (z.B. Flatpak App ID).")
    parser.add_argument('--name', help="Anzeigename der App in Steam.")
    parser.add_argument('--icon', help="Pfad zur Icon-Quelldatei für das Artwork.")
    parser.add_argument('--exe', default='/usr/bin/flatpak', help="Pfad zur auszuführenden Datei.")
    parser.add_argument('--params', help="Startparameter für die Exe.")
    parser.add_argument('--deckstore_logo_path', help="Optional: Pfad zu deinem DeckStore Logo für Branding.")

    args = parser.parse_args()

    userdata_dir = find_steam_userdata_path()
    if not userdata_dir:
        print("FEHLER: Steam Userdata-Verzeichnis nicht gefunden.", file=sys.stderr)
        sys.exit(1)

    exit_code = 1

    if args.action == 'add':
        if not all([args.name, args.icon, args.params]):
            parser.error("--name, --icon und --params sind für die Aktion 'add' erforderlich.")
        success = add_shortcut(
            userdata_dir,
            args.appid_tag,
            args.name,
            args.exe,
            args.params,
            args.icon,
            args.deckstore_logo_path
        )
        exit_code = 0 if success else 1
    elif args.action == 'remove':
        success = remove_shortcut(userdata_dir, args.appid_tag)
        exit_code = 0 if success else 1
    elif args.action == 'check':
        found = check_shortcut(userdata_dir, args.appid_tag)
        exit_code = 0 if found else 1

    sys.exit(exit_code)
