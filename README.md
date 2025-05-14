# Steam Shortcut Manager (Flatpak)

A command-line tool for managing non-Steam game shortcuts within your Steam library, packaged as a Flatpak. This utility allows you to add, remove, and check non-Steam game entries, and can automatically generate and assign various artwork assets to enhance your library's appearance.

## Features

* **Add Applications to Steam:** Seamlessly integrate external applications or games into your Steam library with custom launch parameters.
* **Automatic Artwork Generation:** Creates and assigns a full set of Steam grid artwork:
    * Library Header Capsule (e.g., `appid.png` - 920x430px)
    * Library Portrait/Vertical Capsule (e.g., `appidp.png` - 600x900px)
    * Library Hero (e.g., `appid_hero.png` - 1920x620px)
    * Library Icon (e.g., `appid_icon.png` - 512x512px, transparent)
    * Library Logo (e.g., `appid_logo.png` - max 640x360px, transparent, for overlaying on Hero)
* **Customizable Artwork:**
    * Generates backgrounds with color gradients.
    * Prominently places the app's logo on the generated artwork.
    * Optional branding: Allows for a custom logo (e.g., DeckStore logo) to be discreetly placed on larger artwork pieces.
* **Remove Shortcuts:** Cleanly removes shortcuts previously added by this tool or matching a specific tag.
* **Check Existing Shortcuts:** Verify if a shortcut for a particular application already exists.

## Installation

### From Flathub (Future)

Once officially published on Flathub, you will be able to install it using:
'''bash
flatpak install flathub org.liberavia.steamshortcutmanager
'''
*(Replace `org.liberavia.steamshortcutmanager` with the final, published App ID).*

### Building from Source (For Developers or Early Adopters)

1.  **Clone the Repository:**
    '''bash
    git clone https://github.com/liberavia/steam-shortcut-manager.git 
    cd steam-shortcut-manager
    '''

2.  **Ensure Dependencies are Met:**
    * You need `flatpak` and `flatpak-builder` installed on your system. Refer to your distribution's documentation for installation instructions.

3.  **Build and Install the Flatpak:**
    '''bash
    flatpak-builder --user --install --force-clean build-dir org.liberavia.steamshortcutmanager.json
    '''
    This command builds the Flatpak application, installs it for the current user, and cleans the build directory.

4.  **Run the Application:**
    After a successful build and installation, you can run the tool:
    '''bash
    flatpak run org.liberavia.steamshortcutmanager --help
    '''

## Usage

The tool is operated via the command line.

**General Syntax:**
'''bash
flatpak run org.liberavia.steamshortcutmanager [options]
'''

### Options Explained

* `--action {add,remove,check}`
    * **Description:** Specifies the operation to perform. This is a required argument.
    * `add`: Adds a new non-Steam game shortcut. Requires `--appid_tag`, `--name`, `--icon`, `--exe`, and `--params`.
    * `remove`: Removes an existing non-Steam game shortcut based on its `appid_tag`.
    * `check`: Checks if a shortcut with the given `appid_tag` exists.
    * **Example:** `--action add`

* `--appid_tag APPID_TAG`
    * **Description:** A unique identifier for the application you are managing. This is typically the Flatpak Application ID (e.g., `com.brave.Browser`) or any other string that uniquely identifies the app for this tool. It's used for creating an internal `DeckStore_APPID_TAG` tag in Steam and for the `FlatpakAppID` field in the shortcut data. This is a required argument.
    * **Example:** `--appid_tag "org.videolan.VLC"`

* `--name "APPLICATION NAME"`
    * **Description:** The display name for the application as it will appear in your Steam library. Required for the `add` action.
    * **Example:** `--name "VLC Media Player"`

* `--icon "/path/to/your/icon.png"`
    * **Description:** The absolute path to a source image file (e.g., PNG, JPG) that will be used as the base for generating all Steam artwork. Required for the `add` action.
    * **Example:** `--icon "/home/deck/Pictures/vlc_logo.png"`

* `--exe "/path/to/executable"`
    * **Description:** The absolute path to the primary executable for the application. For Flatpaks, this is usually `/usr/bin/flatpak`. Required for the `add` action.
    * **Default:** `/usr/bin/flatpak`
    * **Example (for a native Linux game):** `--exe "/opt/MyGame/start.sh"`
    * **Example (for Flatpak):** `--exe "/usr/bin/flatpak"`

* `--params "LAUNCH PARAMETERS"`
    * **Description:** The command-line arguments or parameters required to launch the application. For Flatpaks, this is typically `run <flatpak_app_id>`. Required for the `add` action.
    * **Example (for Flatpak):** `--params "run org.videolan.VLC"`
    * **Example (for a native game with arguments):** `--params "--fullscreen --skip-intro"`

* `--deckstore_logo_path "/path/to/branding_logo.png"`
    * **Description:** Optional. An absolute path to an image file (preferably a PNG with transparency) that will be used as a branding logo (e.g., your DeckStore logo). It will be discreetly placed on the generated Hero and Portrait/Grid artwork.
    * **Example:** `--deckstore_logo_path "/home/deck/Pictures/my_deckstore_logo.png"`

### Usage Examples

1.  **Adding a Flatpak Application (e.g., Brave Browser):**
    '''bash
    flatpak run org.liberavia.steamshortcutmanager \
        --action add \
        --appid_tag "com.brave.Browser" \
        --name "Brave Web Browser" \
        --exe "/usr/bin/flatpak" \
        --params "run com.brave.Browser" \
        --icon "/home/deck/Downloads/brave_icon.png" \
        --deckstore_logo_path "/home/deck/assets/deckstore_badge.png" 
    '''

2.  **Adding a Native Linux Game:**
    '''bash
    flatpak run org.liberavia.steamshortcutmanager \
        --action add \
        --appid_tag "mycoolgame_native" \
        --name "My Cool Native Game" \
        --exe "/home/deck/Games/MyCoolGame/start_game.sh" \
        --params "--nogpucheck" \
        --icon "/home/deck/Games/MyCoolGame/artwork/icon.png"
    '''

3.  **Removing an Application:**
    (Assumes `com.brave.Browser` was the `appid_tag` used when adding)
    '''bash
    flatpak run org.liberavia.steamshortcutmanager \
        --action remove \
        --appid_tag "com.brave.Browser"
    '''

4.  **Checking if an Application Shortcut Exists:**
    '''bash
    flatpak run org.liberavia.steamshortcutmanager \
        --action check \
        --appid_tag "com.brave.Browser"
    '''
    *(This will return an exit code: 0 if found, 1 if not found, >1 for an error).*

**Important Notes:**

* **Steam Restart:** After adding or removing shortcuts, you **must restart Steam** for the changes to take full effect and for artwork to update correctly.
* **Absolute Paths:** Always use absolute paths for `--icon`, `--exe` (unless it's a command in PATH like `flatpak`), and `--deckstore_logo_path`.
* **Permissions:** The Flatpak needs appropriate filesystem permissions to access your Steam user data directories and the provided icon paths. The manifest currently uses `--filesystem=host`, which is broad. More specific permissions might be required for Flathub submission.

## License

This project is licensed under the **GNU General Public License v3.0**.
See the `LICENSE` file (to be added, containing GPLv3 text) for the full license text.