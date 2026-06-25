import math
import time
import krpc

# --- CONFIGURATION ---
TARGET_ALTITUDE = 100000  # 100km target orbit
# ---------------------

print("Connecting to KSP...")
try:
    conn = krpc.connect(name='Universal Autopilot - Pro Edition', rpc_port=50120, stream_port=50121)
    print("Connected successfully!")
except:
    print("Error: Make sure 'Start Server' is clicked in KSP!")
    exit()

vessel = conn.space_center.active_vessel
mu = vessel.orbit.body.gravitational_parameter

# Core Telemetry Streams
apoapsis = conn.add_stream(getattr, vessel.orbit, 'apoapsis_altitude')
periapsis = conn.add_stream(getattr, vessel.orbit, 'periapsis_altitude')
altitude = conn.add_stream(getattr, vessel.flight(), 'mean_altitude')
speed = conn.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'speed')
time_to_ap = conn.add_stream(getattr, vessel.orbit, 'time_to_apoapsis')

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

        if apoapsis() >= 70000 and periapsis() >= 70000:
            active_engines = [e for e in vessel.parts.engines if e.active and e.has_fuel]
            if active_engines:
                update_hud("EMERGENCY RETRO-ALIGN", "In Orbit: Activating SAS Retrograde mode...")
                vessel.control.sas = True
                time.sleep(0.1)
                vessel.control.sas_mode = conn.space_center.SASMode.retrograde

                for i in range(6, 0, -1):
                    update_hud("ALIGNING RETROGRADE", f"Swinging rocket around... Burning in {i}s")
                    time.sleep(1)

                vessel.control.throttle = 1.0
                update_hud("EXECUTING DE-ORBIT BURN", "Braking engines firing...")
                time.sleep(6)
                vessel.control.throttle = 0.0
        else:
            print("[ABORT SYSTEM]: Sub-orbital. Skipping turn and burn. Jettisoning capsule instantly!")
            update_hud("SUB-ORBITAL ABORT", "Emergency! Dropping stages instantly...")
            time.sleep(0.1)

        update_hud("VESSEL JETTISON", "Clearing lower vehicle attachments...")
        vessel.control.sas = True
        vessel.control.sas_mode = conn.space_center.SASMode.stability_assist

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
vessel.control.sas = False
vessel.control.throttle = 1.0
vessel.control.abort = False

# Countdown
for i in range(3, 0, -1):
    check_for_abort()
    update_hud("LAUNCH COUNTDOWN", f"T-Minus {i} seconds...")
    time.sleep(1)

print("LIFT-OFF!")
vessel.control.activate_next_stage()
vessel.auto_pilot.engage()
vessel.auto_pilot.target_pitch_and_heading(90, 90)

# --- NEW FEATURE: NASA ROLL PROGRAM ---
# Rolls the rocket over onto its back immediately after clearing the tower
rolled = False
while altitude() < 1000:
    check_for_abort()
    if altitude() > 250 and not rolled:
        vessel.auto_pilot.target_roll = 180  # Orient heads-down for aerodynamic cargo loading
        rolled = True
        update_hud("VERTICAL ASCENT", "Executing roll program...")
    time.sleep(0.02)

# --- PHASE 2: AUTOMATED GRAVITY TURN ---
while apoapsis() < TARGET_ALTITUDE:
    check_for_abort()
    current_alt = altitude()
    execute_intelligent_staging()

    fraction = min(1.0, (current_alt - 1000) / 44000)
    target_pitch = 90.0 - (fraction * 80.0)
    vessel.auto_pilot.target_pitch_and_heading(target_pitch, 90)
    update_hud("GRAVITY TURN", f"Steering East | Target Pitch: {target_pitch:.0f}°")
    time.sleep(0.02)

# --- PHASE 3: COASTING TO SPACE ---
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

    update_hud("COASTING TO SPACE", f"Time to apoapsis: {int(time_to_ap())}s")
    time.sleep(0.02)

# --- NEW FEATURE: MATH-BASED CIRCULARISATION BURN ---
# 1. Calculate orbital math formulas dynamically based on current velocity
r_ap = vessel.orbit.apoapsis  # Current radius at peak from center of planet
v_ap = speed()  # Estimated speed at peak (will refine in real time)

# Vis-Viva Equation to find exactly how much speed (delta-v) we need to add at peak
v_circular = math.sqrt(mu / r_ap)
delta_v = v_circular - v_ap

# Calculate burn length based on active rocket engine thrust properties
F = vessel.available_thrust
Isp = vessel.specific_impulse * 9.81
m0 = vessel.mass
m1 = m0 / math.exp(delta_v / Isp)
flow_rate = F / Isp
burn_time = (m0 - m1) / flow_rate

# 2. Orient the craft perfectly along the horizontal orbital line
vessel.auto_pilot.target_pitch_and_heading(0, 90)
vessel.auto_pilot.target_roll = 0

# 3. Wait until the precise split-second to start firing (Half burn time before peak)
burn_lead_time = burn_time / 2
while time_to_ap() > burn_lead_time:
    check_for_abort()
    update_hud("PRE-BURN ORIENTATION", f"Waiting for burn node... T-Minus {int(time_to_ap() - burn_lead_time)}s")
    time.sleep(0.02)

# 4. Execute the calculated insertion injection burn
vessel.control.throttle = 1.0
while periapsis() < (TARGET_ALTITUDE - 1000):
    check_for_abort()
    execute_intelligent_staging()

    if vessel.thrust == 0.0 and vessel.control.current_stage == 0:
        break

    update_hud("CIRCULARIZATION BURN", f"Injecting Rocket Into Safe Orbit...")
    time.sleep(0.02)

# Shut off engines cleanly
vessel.control.throttle = 0.0
vessel.auto_pilot.disengage()
vessel.control.sas = True
vessel.control.sas_mode = conn.space_center.SASMode.prograde

# --- THE POST-FLIGHT WATCH LOOP ---
while True:
    check_for_abort()
    update_hud("ORBIT ACHIEVED", "Vessel resting safely in target orbit.")

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
    time.sleep(1)
