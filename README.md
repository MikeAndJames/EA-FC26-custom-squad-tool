# EA FC 26 Custom Squad Tool

An advanced Kick Off squad editor, scouting suite, and binary database patcher for **EA SPORTS FC 26**, featuring real-time roster manipulation, reverse-engineered T3DB database parsing, intelligent player scouting, multi-position support, and authentic Prime Icon/Legend management.

---

## 🌟 Key Features

* **Real-Time Binary Squad Patching**: Reverse-engineers and patches EA FC 26 `Squads*` saves and the embedded `T3DB` database in-place, enabling custom player transfers directly into Kick Off without menu grinding.
* **Modern Web Interface**: High-performance, reactive NiceGUI UI with dynamic position rendering, PlayStyle badges, advanced stat filtering, and squad basket builders.
* **100% Authentic Prime Icons & Legends**: Automated extraction and verification of 140+ elite Prime Icons and Heroes (Pelé, Maradona, Zidane, Ronaldo R9, Ronaldinho, Cruyff, Maldini, etc.) directly from game files with official ratings and positions.
* **Multi-Position & Versatility Support**: Full support for Primary and Alternate positions (e.g. Maldini CB/LB, Ronaldinho LW/CAM, Bale RW/LB/ST) with smart positional filtering and tooltip integration.
* **Squad Presets & Backup System**: Save, load, and manage squad transfer presets (e.g. Leeds United Legends) with automated zero-risk backup and restore routines.
* **PlayStyles & Attribute Engine**: Accurate parsing and rendering of signature PlayStyle+ traits and in-game attributes.

---

## 🛠️ Architecture & Tech Stack

* **Backend & Logic**: Python 3.11+
* **UI Framework**: [NiceGUI](https://nicegui.io/) (Fast, modern Python web framework)
* **Binary Database Engine**: Custom LZX decompression and bit-level parser for EA's T3DB database format (`parse_t3db.py`, `swap_players.py`)
* **Data Processing**: Pandas, NumPy
* **Data Sources**: Official EA FC 26 squad binaries, MSMC API, FUT.gg

---

## 🚀 Getting Started

### 1. Prerequisites
* Python 3.11 or higher
* EA SPORTS FC 26 (PC / Steam / EA App)

### 2. Installation
Clone the repository and install the required dependencies:
```bash
git clone https://github.com/MikeAndJames/EA-FC26-custom-squad-tool.git
cd EA-FC26-custom-squad-tool
pip install -r requirements.txt
```

### 3. Launching the App
Run the NiceGUI application:
```bash
python app.py
```
Open your browser at `http://localhost:8080` to search players, build custom squads, and apply transfers!

### 4. Deploying to EA FC 26
To apply your custom squad changes to your active game settings folder:
```bash
deploy_squads.bat
```
*(Select Option 1 to deploy, or Option 2 to pick and patch saved presets)*.

---

## 📂 Project Structure

```text
├── app.py                  # Main NiceGUI web application & squad builder UI
├── icon_database.py        # Icon extraction, official name resolver, and diagnostics
├── player_data.py          # Unified player database loading, filtering, & caching
├── parse_t3db.py           # Bit-level binary parser for EA T3DB database format
├── swap_players.py         # Player transfer & roster byte-level patcher
├── patch_squads.py         # Batch squad file processor & preset executor
├── deploy_squads.bat       # Safe deployment script for game settings on Windows
├── data/                   # Player database datasets, icon names, and merged stats
└── output/                 # Saved squad presets and patched save files
```

---

## 📜 License
This project is for educational, research, and non-commercial modding purposes. EA SPORTS FC is a trademark of Electronic Arts Inc.
