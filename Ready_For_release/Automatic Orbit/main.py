import time
import krpc

# --- CONFIGURATION ---
TARGET_ALTITUDE = 100000  # 100km target orbit
# ---------------------

print("Connecting to KSP...")
try:
    conn = krpc.connect(name='Universal Autopilot - Perfect Safe Orbit', rpc_port=50120, stream_port=50121)
    print("Connected successfully!")
except:
    print("Error: Make sure 'Start Server' is clicked in KSP!")
    exit()

vessel = conn.space_center.active_vessel

# Core Telemetry Streams
apoapsis = conn.add_stream(getattr, vessel.orbit, 'apoapsis_altitude')
periapsis = conn.add_stream(getattr, vessel.orbit, 'periapsis_altitude')
altitude = conn.add_stream(getattr, vessel.flight(), 'mean_altitude')
speed = conn.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'speed')

# --- HUD PANEL SETUP ---
canvas = conn.ui.stock_canvas
ui_panel = canvas.add_text("MISSION COMPUTER: INITIALIZING...")
ui_panel.rect_transform.size = (450, 140)
ui_panel.rect_transform.position = (-350, 300)
ui_panel.color = (0.0, 1.0, 0.4)  # Matrix Green
ui_panel.size = 20


def update_hud(phase, extra_text=""):
    """Refreshes the on-screen display panel with current flight phase and data."""
    ui_panel.content = (
        f"== ORBIT MASTER: INTELLIGENT EYE ==\n"
        f"ACTIVE VESSEL: {vessel.name}\n"
        f"PHASE: {phase}\n"
        f"ALTITUDE: {altitude() / 1000:.1f} km\n"
        f"APOAPSIS: {apoapsis() / 1000:.1f} km | PERIAPSIS: {periapsis() / 1000:.1f} km\n"
        f"{extra_text}\n"
        f"[BACKSPACE TO MANUALLY ABORT]"
    )


def check_for_abort():
    """Monitors KSP's abort group and triggers a direct SAS retrograde burn in space or instant staging."""
    if vessel.control.abort:
        print("\n!!! EMERGENCY INTEL-ABORT SYSTEM ENGAGED !!!")
        ui_panel.color = (1.0, 0.1, 0.1)  # Flash HUD Red

        vessel.control.throttle = 0.0

        # --- CHECK TRAJECTORY PROFILE ---
        # ONLY do the retro-burn routine if BOTH Apoapsis and Periapsis are above 70km (Stable Orbit)
        if apoapsis() >= 70000 and periapsis() >= 70000:
            active_engines = [e for e in vessel.parts.engines if e.active and e.has_fuel]

            if active_engines:
                update_hud("EMERGENCY RETRO-ALIGN", "In Orbit: Activating SAS Retrograde mode...")

                # 1. Turn on KSP's built-in SAS system
                vessel.control.sas = True
                time.sleep(0.1)  # Brief pause to let the game register SAS activation

                # 2. Tell SAS to select the native 'Retrograde' button
                vessel.control.sas_mode = conn.space_center.SASMode.retrograde

                # 3. Give the ship 6 seconds to physically swing around backward
                # No complex vector formulas to crash or bug out!
                for i in range(6, 0, -1):
                    update_hud("ALIGNING RETROGRADE", f"Swinging rocket around... Burning in {i}s")
                    time.sleep(1)

                # 4. Safely fire the stopping braking engines
                vessel.control.throttle = 1.0
                update_hud("EXECUTING DE-ORBIT BURN", "Braking engines firing...")
                time.sleep(6)
                vessel.control.throttle = 0.0
        else:
            # --- SUB-ORBITAL DETECTED: NO SPINNING, JUST INSTANT STAGE ---
            print("[ABORT SYSTEM]: Sub-orbital. Skipping turn and burn. Jettisoning capsule instantly!")
            update_hud("SUB-ORBITAL ABORT", "Emergency! Dropping stages instantly...")
            time.sleep(0.1)

        # --- INSTANT CASCADE STAGING DECOUPLER ---
        update_hud("VESSEL JETTISON", "Clearing lower vehicle attachments...")
        vessel.control.sas = True
        vessel.control.sas_mode = conn.space_center.SASMode.stability_assist  # Reset SAS to normal hold

        while vessel.control.current_stage > 0:
            try:
                vessel.control.activate_next_stage()
                time.sleep(0.4)
            except:
                break

        update_hud("CAPSULE RECOVERY", "Deploying safety recovery parachutes...")
        vessel.control.chutes = True

        time.sleep(5)
        ui_panel.remove()
        print("[MISSION COMPUTER]: Abort sequence complete. Exiting.")
        exit()


def execute_intelligent_staging():
    """Scans the active parts tree and stages dynamically if any engine group runs dry."""
    active_engines = [e for e in vessel.parts.engines if e.active]
    if not active_engines:
        return

    should_stage = False
    for engine in active_engines:
        if not engine.has_fuel:
            should_stage = True
            break
        if engine.part.stage == vessel.control.current_stage and engine.thrust == 0.0:
            should_stage = True
            break

    if should_stage:
        print("\n[STAGING BRAIN]: Flameout detected. Executing clean decoupling...")
        vessel.control.activate_next_stage()
        time.sleep(0.6)


# Initialize Controls
vessel.control.sas = True
vessel.control.throttle = 1.0
vessel.control.abort = False

# Countdown
for i in range(3, 0, -1):
    check_for_abort()
    update_hud("LAUNCH COUNTDOWN", f"T-Minus {i} seconds...")
    time.sleep(1)

print("LIFT-OFF!")
vessel.control.activate_next_stage()

# --- PHASE 1 & 2: LAUNCH & AUTOMATED GRAVITY TURN ---
turn_started = False
while apoapsis() < TARGET_ALTITUDE:
    check_for_abort()
    current_alt = altitude()
    execute_intelligent_staging()

    if current_alt > 1000:
        if not turn_started:
            vessel.auto_pilot.engage()
            turn_started = True

        fraction = min(1.0, (current_alt - 1000) / 44000)
        target_pitch = 90.0 - (fraction * 80.0)
        vessel.auto_pilot.target_pitch_and_heading(target_pitch, 90)
        update_hud("GRAVITY TURN", f"Steering East | Target Pitch: {target_pitch:.0f}°")
    else:
        update_hud("VERTICAL ASCENT", "Clearing launch pad towers...")

    time.sleep(0.02)

# --- PHASE 3: COASTING TO SPACE & DEPLOYMENT ---
vessel.control.throttle = 0.0
vessel.auto_pilot.target_pitch_and_heading(0, 90)
systems_deployed = False

while altitude() < 70000:
    check_for_abort()
    execute_intelligent_staging()

    if altitude() > 50000 and not systems_deployed:
        update_hud("SYSTEM DEPLOYMENT", "Deploying solar panels and antennas...")
        vessel.control.solar_panels = True
        vessel.control.antennas = True
        vessel.control.toggle_action_group(1)
        systems_deployed = True
        time.sleep(1)

    time_to_space = int((70000 - altitude()) / max(1, speed()))
    update_hud("COASTING TO SPACE", f"Time to space boundary: {time_to_space}s")
    time.sleep(0.02)

# --- PHASE 4: SPACE OPERATIONS & ORIENTATION ---
vessel.control.sas = True
time.sleep(1)
vessel.control.sas_mode = conn.space_center.SASMode.prograde

while True:
    check_for_abort()
    distance_to_peak = apoapsis() - altitude()
    if distance_to_peak <= 5000:
        break
    update_hud("PRE-BURNS ORIENTATION", f"Coasting to Peak | Distance to Burn: {distance_to_peak / 1000:.1f} km")
    time.sleep(0.02)

# Execute final circularization injection burn early
vessel.control.throttle = 1.0
while periapsis() < (TARGET_ALTITUDE - 2000):
    check_for_abort()
    execute_intelligent_staging()

    if vessel.thrust == 0.0 and vessel.control.current_stage == 0:
        break

    update_hud("CIRCULARIZATION BURN", f"Injecting Rocket Into Safe Orbit...")
    time.sleep(0.02)

# Shut off engines
vessel.control.throttle = 0.0
vessel.auto_pilot.disengage()

# --- THE POST-FLIGHT WATCH LOOP ---
# Only loops here if the launch script ran all the way through to completion!
while True:
    check_for_abort()

    # Automatic check: If both points are still sub-orbital, bail out the capsule
    if apoapsis() < 70000 and periapsis() < 70000:
        print("\n!!! FAIL-SAFE ACCIDENT RESPONSE ACTUATED !!!")
        ui_panel.color = (1.0, 0.5, 0.0)
        vessel.control.throttle = 0.0
        while vessel.control.current_stage > 0:
            try:
                vessel.control.activate_next_stage()
                time.sleep(0.4)
            except:
                break
        vessel.control.chutes = True
        ui_panel.remove()
        exit()

    update_hud("MISSION ACCOMPLISHED", "Status: Stable Orbit Established. Computer Idle.")
    vessel.control.sas_mode = conn.space_center.SASMode.prograde
    time.sleep(1)
