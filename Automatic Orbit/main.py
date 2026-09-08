import math
import time
import krpc

# --- CONFIGURATION INITIALIZATION ---
TARGET_ALTITUDE = 100000  # 100km target orbit

# --- INTERACTIVE ORBIT INPUT ---
print("====================================")
print("     LAUNCH TRAJECTORY SELECTOR     ")
print("====================================")
print("1) Equatorial Orbit (Standard Eastward)")
print("2) Polar Orbit (Northward Over the Poles)")
choice = input("Select orbit type (1 or 2): ").strip()

print("\nConnecting to KSP...")
try:
    conn = krpc.connect(name='Universal Autopilot - Precision Edition', rpc_port=50120, stream_port=50121)
    print("Connected successfully!")
except:
    print("Error: Make sure 'Start Server' is clicked in KSP!")
    exit()

vessel = conn.space_center.active_vessel
body = vessel.orbit.body
mu = body.gravitational_parameter

# This adjusts our launch heading so Kerbin's rotation doesn't ruin the polar angle
r_surface = body.equatorial_radius
rotational_period = body.rotational_period
v_planet_rot = (2 * math.pi * r_surface) / rotational_period  # ~174.5 m/s on Kerbin

# Vis-Viva calculation to find our expected target orbital speed at 100km
v_target_orbital = math.sqrt(mu / (r_surface + TARGET_ALTITUDE))

if choice == "2":
    # Trigonometry to cancel out the planet moving sideways underneath us
    # This points the rocket slightly Northwest so the net track is perfectly North
    correction_angle = math.degrees(math.asin(v_planet_rot / v_target_orbital))
    TARGET_HEADING = (360 - correction_angle) % 360
    TARGET_ROLL = 90
    orbit_type_str = f"POLAR (Steering Heading: {TARGET_HEADING:.1f}°)"
else:
    TARGET_HEADING = 90  # Standard East launch uses the planet's boost
    TARGET_ROLL = 180
    orbit_type_str = "EQUATORIAL (EAST)"

print(f"Trajectory parameters locked: {orbit_type_str}")

apoapsis = conn.add_stream(getattr, vessel.orbit, 'apoapsis_altitude')
periapsis = conn.add_stream(getattr, vessel.orbit, 'periapsis_altitude')
altitude = conn.add_stream(getattr, vessel.flight(), 'mean_altitude')
speed = conn.add_stream(getattr, vessel.flight(body.reference_frame), 'speed')
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
        f"== ORBIT MASTER: PRECISION EYE ==\n"
        f"ACTIVE VESSEL: {vessel.name}\n"
        f"PHASE: {phase}\n"
        f"ALTITUDE: {altitude() / 1000:.1f} km\n"
        f"APOAPSIS: {apoapsis() / 1000:.1f} km | PERIAPSIS: {periapsis() / 1000:.1f} km\n"
        f"{extra_text}\n"
        f"[BACKSPACE TO MANUALLY ABORT]"
    )


def check_for_abort():
    """Monitors KSP's abort group and triggers a emergency escape profiles."""
    if vessel.control.abort:
        print("\n!!! EMERGENCY ABORT SYSTEM ENGAGED !!!")
        ui_panel.color = (1.0, 0.1, 0.1)
        vessel.control.throttle = 0.0

        if apoapsis() >= 70000 and periapsis() >= 70000:
            active_engines = [e for e in vessel.parts.engines if e.active and e.has_fuel]
            if active_engines:
                update_hud("In Orbit: Activating SAS Retrograde mode...")
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
            print("[ABORT SYSTEM]: Sub-orbital. Jettisoning capsule!")
            update_hud("SUB-ORBITAL ABORT", "Emergency! Dropping stages...")
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
        print("\n[STAGING BRAIN]: Flameout detected.")
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
vessel.auto_pilot.target_pitch_and_heading(90, TARGET_HEADING)

# --- ADJUSTED ROLL PROGRAM ---
rolled = False
while altitude() < 1000:
    check_for_abort()
    if altitude() > 150 and not rolled:
        vessel.auto_pilot.target_roll = TARGET_ROLL
        rolled = True
    update_hud("VERTICAL ASCENT", f"Executing roll program for {choice}...")
    time.sleep(0.02)

# --- PHASE 2: AUTOMATED GRAVITY TURN ---
while apoapsis() < TARGET_ALTITUDE:
    check_for_abort()
    current_alt = altitude()
    execute_intelligent_staging()

    fraction = min(1.0, (current_alt - 1000) / 44000)
    target_pitch = 90.0 - (fraction * 80.0)
    vessel.auto_pilot.target_pitch_and_heading(target_pitch, TARGET_HEADING)
    update_hud("GRAVITY TURN", f"Steering Trajectory | Target Pitch: {target_pitch:.0f}°")
    time.sleep(0.02)

# --- PHASE 3: COASTING TO SPACE ---
vessel.control.throttle = 0.0
vessel.auto_pilot.target_pitch_and_heading(0, TARGET_HEADING)
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

# Recalculates dynamically right before the burn based on actual achieved trajectory speed
r_ap = vessel.orbit.apoapsis
v_ap = speed()

# Vis-Viva calculation to find exact target speed required for circular velocity at this exact apoapsis height
v_circular = math.sqrt(mu / r_ap)
delta_v = v_circular - v_ap

# Compute exact engine burn metrics using Rocket Equations
F = vessel.available_thrust
Isp = vessel.specific_impulse * 9.81
m0 = vessel.mass
m1 = m0 / math.exp(delta_v / Isp)
flow_rate = F / Isp
burn_time = (m0 - m1) / flow_rate

# Dynamically point Prograde relative to our real vector path, not just a blind compass heading
vessel.auto_pilot.target_pitch_and_heading(0, TARGET_HEADING)
vessel.auto_pilot.target_roll = 0

burn_lead_time = burn_time / 2
while time_to_ap() > burn_lead_time:
    check_for_abort()
    update_hud("PRE-BURN ORIENTATION", f"Waiting for burn node... T-Minus {int(time_to_ap() - burn_lead_time)}s")
    time.sleep(0.02)

# Execute the precision injection velocity burn
vessel.control.throttle = 1.0
while periapsis() < (TARGET_ALTITUDE - 1000):
    check_for_abort()
    execute_intelligent_staging()

    if vessel.thrust == 0.0 and vessel.control.current_stage == 0:
        break

    update_hud("CIRCULARIZATION BURN", f"Injecting Rocket Into Safe {choice} Orbit...")
    time.sleep(0.02)

vessel.control.throttle = 0.0
vessel.auto_pilot.disengage()
vessel.control.sas = True
vessel.control.sas_mode = conn.space_center.SASMode.prograde

while True:
    check_for_abort()
    update_hud("ORBIT ACHIEVED", f"Vessel resting safely in target orbit.")

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
