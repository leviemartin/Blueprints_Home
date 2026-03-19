# How to Disable the LG Air Conditioner Beep

Your LG air conditioner makes a "ping" (beep) every time it receives a command — whether from the IR remote, the LG ThinQ app, or Home Assistant. This is a firmware-level confirmation tone that **cannot be disabled through software** via the ThinQ API.

This guide covers two workarounds, from simplest to most capable.

---

## Table of Contents

- [Option 1: Physically Mute the Buzzer](#option-1-physically-mute-the-buzzer)
- [Option 2: ESPHome Wired Controller (Recommended)](#option-2-esphome-wired-controller-recommended)
- [Which Option Should I Choose?](#which-option-should-i-choose)

---

## Option 1: Physically Mute the Buzzer

The beep comes from a small piezoelectric buzzer soldered onto the indoor unit's PCB. You can muffle or disconnect it.

### What You Need

| Item | Notes |
|---|---|
| Phillips screwdriver | To open the unit's electrical cover |
| Electrical tape | For the non-destructive method |
| Flashlight | The PCB is inside a dark compartment |
| (Optional) Soldering iron or small wire cutters | For the permanent method |

**Cost: Free** (assuming you have basic tools)

### Safety First

> **WARNING: Mains voltage (230V/120V) is present inside the unit. Always turn off the circuit breaker — not just the remote — before opening the unit. Wait 30 seconds after powering off. Do not touch large capacitors on the PCB.**

### Step 1: Access the PCB

1. **Turn off the circuit breaker** that feeds your AC unit.
2. **Open the front panel** of the indoor unit — on most LG wall-mount units, grip both sides and lift upward. It hinges open.
3. **Remove the air filters** to get better visibility.
4. **Locate the electrical compartment** — a metal cover on the right-hand side of the unit. Remove the screws holding it.
5. Inside you will see the main PCB (circuit board).

### Step 2: Find the Buzzer

The buzzer is a **small, round, black disc** (about 10-15mm across) mounted on the PCB. It is usually labeled **"BUZZER"** or **"BZ"** on the circuit board's silkscreen (the white text printed on the board).

### Step 3: Choose Your Method

#### Method A: Tape Over It (Easiest, Fully Reversible)

1. Place a piece of **electrical tape** firmly over the buzzer's sound hole.
2. For extra muffling, fold the tape over itself a few times to create a thick pad, then press it onto the buzzer.
3. **Result:** Significantly quieter but not fully silent.
4. **Reversible:** Yes — just peel off the tape.
5. **Warranty impact:** None.

#### Method B: Disconnect It (Permanent, Fully Silent)

**If the buzzer has wires or a connector:**
1. Simply unplug the connector, or cut one wire.
2. You can reconnect later if needed.

**If the buzzer is soldered directly to the PCB (more common):**
1. Use a soldering iron to desolder **one leg** of the buzzer from the PCB. OR
2. Use small wire cutters to snip one leg flush with the buzzer body. OR
3. Use needle-nose pliers to gently rock and pull the buzzer off the PCB pads.

> **Be careful:** Only work on the buzzer itself. Damaging nearby traces or components could cause issues. This method will void any warranty on the PCB.

4. **Result:** Completely silent.
5. **Reversible:** Only if desoldered cleanly — you can re-solder it.

#### Method C: Inline Toggle Switch (Best of Both Worlds)

If the buzzer has wires, you can splice a small toggle switch inline. This lets you enable/disable the beep at will — useful if you sometimes want the beep (e.g., to confirm the IR remote reached the unit).

### What This Does and Doesn't Solve

- **Solves:** The beep from IR remote, ThinQ app, and Home Assistant commands.
- **Does not solve:** You still need the ThinQ cloud integration (with its latency and cloud dependency) to control the AC from Home Assistant.
- **The AC still beeps internally at the outdoor unit** during defrost cycles and similar — this only silences the indoor unit's buzzer.

---

## Option 2: ESPHome Wired Controller (Recommended)

This is the proper solution. Instead of using the LG ThinQ cloud, you connect an ESP32 microcontroller directly to the AC's internal wired controller port. Commands sent this way **do not trigger the beep** because the AC treats it like an official LG wired wall controller, not a remote command.

**Bonus:** It's fully local (no cloud dependency), near-instant response, and gives you more control than the ThinQ integration.

### How It Works

Your LG indoor unit has a port called **CN-REMO** — this is where LG's official wired wall controllers (like the PREMTB100) plug in. The open-source project [esphome-lg-controller](https://github.com/JanM321/esphome-lg-controller) reverse-engineered the protocol and built a custom PCB that an ESP32 plugs into. The ESP32 connects to your Wi-Fi and appears in Home Assistant as a climate entity via ESPHome.

### Before You Start: Check Compatibility

Your LG S3-M18KL1MA should have the CN-REMO port, but verify before ordering parts:

1. Turn off the circuit breaker.
2. Open the indoor unit (lift front panel, remove filter, unscrew electrical cover).
3. Look for a **green 3-pin connector** on the PCB labeled **CN-REMO**.
4. If it's there, you're good. Take a photo for reference.
5. Some units have a short extension cable already plugged into CN-REMO — that's fine, you'll plug into the end of that cable.

> **Tip:** Your installation manual should also reference "wired remote controller" compatibility and list PREMTB100 or PREMTA200 as compatible accessories. This confirms CN-REMO is present.

### What You Need to Buy

| Item | What It Is | Approx. Cost | Where to Buy |
|---|---|---|---|
| **Custom PCB (hardware-tiny)** | Pre-assembled board with voltage regulator and signal converter | ~$10-12 per board ($50 for min. order of 5) | [JLCPCB](https://jlcpcb.com) with assembly service |
| **ESP32-DevKitC-32E** | The microcontroller board — has Wi-Fi, plugs into the custom PCB | ~$8-15 | [Amazon](https://www.amazon.com/s?k=ESP32-DevKitC-32E), AliExpress, DigiKey |
| **Adafruit 4873 cable** | 3-pin JST-XH cable (2.5mm pitch) — connects PCB to AC's CN-REMO port | ~$1.50 | [Adafruit](https://www.adafruit.com/product/4873), Amazon |
| **Micro-USB cable** | For initial firmware flashing (one-time, then updates go over Wi-Fi) | ~$3-5 | Any electronics store |
| **Small enclosure (optional)** | To house the PCB neatly inside or outside the AC unit | ~$5 | Amazon, or 3D-print one |

**Total cost: ~$25-35 per AC unit** (or ~$15/unit if you use the extra PCBs from the minimum order of 5).

### Step-by-Step Setup

#### Part A: Order the Custom PCB

The custom PCB converts the AC's 12V signal to something the ESP32 can understand. You don't have to solder anything — JLCPCB assembles it for you.

1. Go to [github.com/JanM321/esphome-lg-controller](https://github.com/JanM321/esphome-lg-controller).
2. Download or clone the repository.
3. Navigate to the `hardware-tiny/production/` folder. You'll find three files:
   - `GERBER-lg_hvac_esp32.zip` (PCB design)
   - `bom.csv` (bill of materials — the components)
   - `positions.csv` (where to place the components)
4. Go to [jlcpcb.com](https://jlcpcb.com) and click **"Order Now"** or **"Instant Quote"**.
5. Upload `GERBER-lg_hvac_esp32.zip`. Leave all PCB settings at their defaults.
6. Scroll down and toggle **"PCB Assembly"** on.
7. Upload `bom.csv` as the BOM file and `positions.csv` as the CPL file.
8. JLCPCB will source and solder all the tiny components onto the board for you.
9. The minimum order is 5 boards. Manufacturing + shipping takes ~1-2 weeks.

> **What's on the PCB:** A LIN transceiver chip (converts the AC's 12V serial signal to 3.3V for the ESP32), a voltage regulator (powers the ESP32 from the AC's 12V supply), and supporting passive components. All pre-soldered.

#### Part B: Flash the ESP32 Firmware

This step programs the ESP32 to speak the LG protocol and connect to your Wi-Fi.

**Prerequisites:**
- A computer (Mac, Windows, or Linux)
- Python 3 installed ([python.org/downloads](https://www.python.org/downloads/))
- Your Wi-Fi network name (SSID) and password

**Steps:**

1. **Install ESPHome** on your computer:
   ```bash
   pip install esphome
   ```

2. **Navigate to the esphome folder** in the cloned repository:
   ```bash
   cd esphome-lg-controller/esphome
   ```

3. **Copy the template configuration:**
   ```bash
   cp template.yaml lg-ac-ground-floor.yaml
   ```
   (Use a descriptive name for your floor)

4. **Edit the configuration file** — open `lg-ac-ground-floor.yaml` in any text editor and change every line marked with `# XXX`:

   ```yaml
   substitutions:
     deviceid: "lg-ac-ground"           # Unique ID, lowercase, no spaces
     devicename: "LG AC Ground Floor"    # Friendly name shown in HA
     temperature_sensor_entity_id: "sensor.ground_floor_temperature"
                                         # Your Aqara sensor entity ID
     fahrenheit: "false"                 # Set to "true" for Fahrenheit

   api:
     encryption:
       key: "your-generated-key-here"    # Generate with: esphome generate-api-key

   wifi:
     ssid: "YourWiFiName"
     password: "YourWiFiPassword"
     manual_ip:
       static_ip: 192.168.1.50          # Pick an unused IP on your network
       gateway: 192.168.1.1
       subnet: 255.255.255.0

   ap:
     password: "fallback-hotspot-pw"     # Fallback hotspot if Wi-Fi fails
   ```

   > **The `temperature_sensor_entity_id` is key:** This tells the ESP32 to feed your Aqara sensor's reading to the AC unit, replacing its unreliable built-in thermistor. The AC then uses this accurate reading for its own internal thermostat logic.

5. **Connect the ESP32 to your computer** via micro-USB.

6. **Flash the firmware:**
   ```bash
   esphome run lg-ac-ground-floor.yaml
   ```
   ESPHome will compile and upload the firmware. You'll see logs showing the ESP32 connecting to your Wi-Fi.

7. **Disconnect the USB cable.** From now on, firmware updates happen over Wi-Fi (OTA).

#### Part C: Assemble the Hardware

1. **Mount the ESP32 onto the custom PCB** — it plugs into the female pin headers on the PCB. Line up the pins carefully and press down firmly.
2. **Connect the JST-XH cable** (Adafruit 4873) to the 3-pin header on the custom PCB.

#### Part D: Install in the AC Unit

1. **Turn off the circuit breaker.**
2. **Open the indoor unit** (same as the compatibility check step).
3. **Plug the JST-XH cable into CN-REMO.** Match the wire colors to the pinout:

   | Pin | Wire Color | Function |
   |---|---|---|
   | 1 | Red | +12V DC (power) |
   | 2 | Yellow | Signal (data) |
   | 3 | Black | GND (ground) |

   > **CRITICAL: Double-check the wire colors before powering on.** Reversing 12V and GND will damage the board.

4. **Route the cable** so it doesn't contact hot or moving parts.
5. **(Optional)** Place the PCB + ESP32 in a small enclosure and mount it inside the AC unit or on the wall nearby.
6. **Close up the unit** and turn the breaker back on.
7. The AC's 12V supply powers the ESP32 — no separate power adapter needed.

#### Part E: Add to Home Assistant

1. In Home Assistant, go to **Settings > Devices & Services**.
2. The ESPHome device should auto-discover. If not, click **"Add Integration"** > **"ESPHome"** and enter the static IP you configured (e.g., `192.168.1.50`).
3. Enter the **encryption key** from your YAML file when prompted.
4. A new climate entity appears (e.g., `climate.lg_ac_ground_floor`).

You can now control the AC from Home Assistant — and **it won't beep**.

#### Part F: Repeat for the Second Floor

Follow the same steps with a different configuration file (`lg-ac-first-floor.yaml`), a different `deviceid`, and a different static IP.

### What You Get in Home Assistant

| Entity Type | What It Controls |
|---|---|
| **Climate** | Mode (off/auto/cool/heat/dry/fan), target temp, fan speed, swing |
| **Number** | Vane positions (1-4), fan speed fine-tuning, sleep timer |
| **Switch** | External thermistor toggle, air purifier, auto clean |
| **Sensor** | Outdoor unit status, defrost, error codes, pipe temperatures |

### Can I Keep Using ThinQ and the Remote?

**Yes.** The ESPHome controller, ThinQ app, and IR remote all coexist. Settings sync bidirectionally — if you change the temperature with the remote, Home Assistant sees the update. If you change it from HA, the remote's display updates too.

The only difference: commands from the ESPHome controller don't beep. Commands from the remote and ThinQ app still will (unless you also physically mute the buzzer per Option 1).

### ESPHome Controller vs. ThinQ Cloud — Comparison

| | ESPHome Wired | LG ThinQ Cloud |
|---|---|---|
| Internet required | No (fully local) | Yes |
| Response time | Near-instant | Seconds (cloud round-trip) |
| AC beeps on command | **No** | Yes |
| If LG shuts down servers | Still works | Stops working |
| Use your own temp sensor | Yes (feeds directly to AC) | No |
| Setup difficulty | Moderate | Easy |
| Cost | ~$25-35 per unit | Free |
| Vane angle control | Per-vane (up to 4) | Limited |
| Display light control | Not available | Available |

### Troubleshooting

**ESP32 doesn't connect to Wi-Fi:**
- Check SSID and password in the YAML file.
- The ESP32 creates a fallback hotspot (name = `devicename`, password = `ap: password`). Connect to it at `192.168.4.1` to reconfigure.

**AC doesn't respond to commands:**
- Verify the JST-XH cable is firmly seated in CN-REMO.
- Check wire color order: Red=12V, Yellow=Signal, Black=GND.
- Check ESPHome logs: `esphome logs lg-ac-ground-floor.yaml`

**AC works but temperature readings are wrong:**
- Verify the `temperature_sensor_entity_id` in your YAML points to a valid HA sensor.
- The AC takes a few minutes to switch from its internal thermistor to the external sensor.

**You want to revert to ThinQ-only:**
- Simply unplug the JST-XH cable from CN-REMO. The AC returns to normal.

---

## Which Option Should I Choose?

| Scenario | Recommendation |
|---|---|
| I just want it quieter, minimal effort | **Option 1A** — tape over the buzzer |
| I want full silence + keep using ThinQ | **Option 1B** — disconnect the buzzer |
| I want silence + local control + better temperature accuracy | **Option 2** — ESPHome wired controller |
| I want the best possible setup for HA automations | **Option 2** — pairs perfectly with the LG AC Climate Control blueprint |

**For your setup** (2 floors, Aqara sensors, Home Assistant automations), **Option 2 is the clear winner.** It eliminates the beep, gives you local control without cloud dependency, and lets you feed the Aqara temperature readings directly to the AC unit. The ~$25-35 per unit investment pays for itself in reliability and silence.

---

## Sources

- [esphome-lg-controller GitHub](https://github.com/JanM321/esphome-lg-controller) — Source code, PCB designs, tested models
- [esphome-lg-controller Wiki](https://github.com/JanM321/esphome-lg-controller/wiki) — Compatibility list, advanced configuration
- [Home Assistant Community Thread](https://community.home-assistant.io/t/lg-ac-wired-controller-integration-via-esphome-esp32/582954) — Installation photos, Q&A
- [ESPHome Installation Guide](https://esphome.io/guides/installing_esphome.html) — Official ESPHome setup docs
- [Adafruit 4873 Cable](https://www.adafruit.com/product/4873) — JST-XH connector cable
- [JLCPCB Assembly Service](https://jlcpcb.com) — PCB manufacturing and assembly
