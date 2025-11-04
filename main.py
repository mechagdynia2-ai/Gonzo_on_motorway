import flet as ft, asyncio, random
from flet import canvas as cv
from dataclasses import dataclass
from collections import defaultdict

# ---- Audio migration: We ONLY use flet_audio ----
#
# IMPORTANT: The old ft.Audio module (which you used as a fallback)
# is deprecated and CAUSES "unknown control" errors and no sound on Android.
#
# For this version to work, you MUST add `flet_audio` to your project
# dependencies (e.g., in requirements.txt if building an APK).
#
# The correct command is:
# pip install flet_audio
#
try:
    from flet_audio import Audio as AudioCtrl
except ImportError:
    print("="*80)
    print(" ERROR: 'flet_audio' module not found. ")
    print(" The game will have no sound and may not work correctly on mobile.")
    print(" Install it using: pip install flet_audio")
    print(" And add 'flet_audio' to your requirements.txt before building the APK.")
    print("="*80)
    # Create a dummy class so the program can run, but nothing will play
    class AudioCtrl:
        def __init__(self, *args, **kwargs): pass
        def play(self): print("Audio-Stub: Play")
        def update(self): pass
        def on_ended(self, *args): pass
        def seek(self, *args): pass
        volume = 0.0
        src = ""
        autoplay = False


# --- Config (start; will be recalculated on resize) ---
W, H, GRID = 800, 600, 40
# START_X is now calculated dynamically (W // 2)
LANES_Y = [GRID * 4, GRID * 6, GRID * 8, GRID * 10]
START_X, START_Y, PLAYER_SIZE = W // 2, GRID * 13, GRID
# GAMEPLAY FIX: Increased MIN_GAP to prevent cars bunching up
FPS_SLEEP, MAX_LEVEL, MIN_GAP = 0.05, 60, int(GRID * 1.5) # Było 0.75
HEART_RED, HEART_WHITE = "#ff3b30", "#ffffff"

ANIM_DT_TICKS = 2         # 0.1 s at FPS_SLEEP=0.05
HONK_REACT_TICKS = 10     # 0.5 s
IDLE_RANDOM_AFTER = 100   # 5.0 s without movement

def rects_intersect(ax, ay, aw, ah, bx, by, bw, bh):
    return (ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by)

# --- colors / shadows ---
def _clamp(x, a=0, b=255): return max(a, min(b, int(x)))
def _hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3: h = "".join([c * 2 for c in h])
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
def _rgb_to_hex(rgb): return "#" + "".join(f"{_clamp(c):02x}" for c in rgb)
def shade(hex_color: str, factor: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    if factor >= 1:
        r = r + (255 - r) * (factor - 1)
        g = g + (255 - g) * (factor - 1)
        b = b + (255 - b) * (factor - 1)
    else:
        r *= factor; g *= factor; b *= factor
    return _rgb_to_hex((int(r), int(g), int(b)))

# Paint helpers
FILL = lambda color: ft.Paint(color=color)
STROKE = lambda color, w=2: ft.Paint(color=color, stroke_width=w, style=ft.PaintingStyle.STROKE)

def RRECT(x, y, w, h, r, paint):
    if hasattr(cv, "RRect"):
        return cv.RRect(x, y, w, h, r, paint=paint)
    # Fallback for older Flet versions (or where RRect isn't available)
    return cv.Rect(x, y, w, h, paint=paint)

@dataclass
class BloodStain:
    x: float; y: float; t: int = 0; max_t: int = 30 # Changed from 60 to 30 for faster fade
    def alive(self): return self.t < self.max_t
    def step(self): self.t += 1

@dataclass
class Car:
    y: float; speed: float; length: float; color: str; x: float
    honk_timer: int = 0
    def is_near(self, px, py):
        if py != self.y: return False
        thr = 4 * GRID
        return ((self.speed > 0 and self.x + self.length < px and px - (self.x + self.length) < thr) or
                (self.speed < 0 and px + PLAYER_SIZE < self.x and self.x - (px + PLAYER_SIZE) < thr))
    def collides(self, px, py):
        return rects_intersect(px, py, PLAYER_SIZE, PLAYER_SIZE, self.x, self.y, self.length, GRID)

class GonzoGame:
    SPEED_SEGMENTS = [(20, 1), (30, 4), (35, 6), (38, 10), (40, 30), (45, 40),
                      (50, 50), (55, 60), (58, 70), (60, 100)]
    BASE_STEP, START_MULT = 0.12, 1.8

    # --- sprite files ---
    SPRITES = {
        "START": "assets/START.POSITION.06.png",
        "FUCK":  "assets/FUCK.OFF.09.png",
        "STEP_FRONT": [
            "assets/01.STEP.FRONT.03.png",
            "assets/02.STEP.FRONT.07.png",
            "assets/03.STEP.FRONT.08.png",
        ],
        "LOOK_BACK":  "assets/LOOK.BACK.02.png",
        "STEP_BACK":  "assets/STEP.BACK.04.png",
        "LOOK_LEFT":  "assets/LOOK.LEFT.01.png",
        "LOOK_RIGHT": "assets/LOOK.RIGHT.05.png",
    }

    ALL_SPRITES_FOR_IDLE = [
        "assets/01.STEP.FRONT.03.png",
        "assets/02.STEP.FRONT.07.png",
        "assets/03.STEP.FRONT.08.png",
        "assets/FUCK.OFF.09.png",
        "assets/LOOK.BACK.02.png",
        "assets/LOOK.LEFT.01.png",
        "assets/LOOK.RIGHT.05.png",
        "assets/START.POSITION.06.png",
        "assets/STEP.BACK.04.png",
    ]

    def __init__(self, page: ft.Page):
        self.p = page
        self.p.title = "Gonzo on Motorway — Flet (Responsive Canvas + Audio + Sprites)"
        self.p.on_keyboard_event = self.on_key
        self.p.padding = 0
        self.p.window_maximized = True

        # Handle window resizing (phone/rotation)
        self.p.on_resize = self._on_resize

        self.p.appbar = ft.AppBar(
            title=ft.Text("Gonzo on Motorway"),
            center_title=False,
            bgcolor=ft.Colors.with_opacity(0.05, "#ffffff"),
            actions=[ft.TextButton("Close", on_click=lambda e: self.exit_game())],
        )

        # --- AUDIO (flet_audio only) ---
        self._sfx_pool_idx = {"honk": 0, "step": 0}
        self.sfx = {
            "hit":   [AudioCtrl(src="assets/hit.wav", volume=1.0)],
            "level": [AudioCtrl(src="assets/level.wav", volume=1.0)],
            "honk":  [AudioCtrl(src="assets/honk.wav", volume=0.5) for _ in range(3)],
            "step":  [AudioCtrl(src="assets/step.wav", volume=0.35) for _ in range(2)],
        }
        self._bgm_tracks = [f"assets/audio{str(i).zfill(2)}.wav" for i in range(1, 9)]
        self._last_bgm = None
        self.bgm = AudioCtrl(src=self._pick_next_bgm(), volume=0.25, autoplay=True)
        self.bgm.on_ended = lambda e: self._bgm_next()
        
        # Add audio controls to page overlay (required)
        for lst in self.sfx.values():
            for a in lst:
                self.p.overlay.append(a)
        self.p.overlay.append(self.bgm)
        self.p.update() # Required to register audio controls

        def _play_sfx(key: str):
            if key not in self.sfx: return
            try:
                a = None
                if key in ("honk", "step"):
                    i = self._sfx_pool_idx[key]
                    a = self.sfx[key][i]
                    self._sfx_pool_idx[key] = (i + 1) % len(self.sfx[key])
                else:
                    a = self.sfx[key][0]
                
                # AUDIO FIX: Must seek(0) to replay audio on mobile
                a.seek(0)
                a.play()
            except Exception as e:
                print(f"Error playing sfx '{key}': {e}")
        self._play_sfx = _play_sfx

        # --- state ---
        self.level = 1; self.score = 0; self.lives = 4; self.game_over = False; self.tick = 0
        self.checkpoint_level = 1; self.checkpoint_score = 0

        # --- PLAYER: Image in a Container (scalable) ---
        self.player_img = ft.Image(src=self.SPRITES["START"], fit=ft.ImageFit.CONTAIN)
        self.player = ft.Container(content=self.player_img)

        # sprite animation
        self.anim_tick_acc = 0
        self.last_move_tick = 0
        self.move_anim_until = 0
        self.current_dir = "front"
        self.step_front_idx = 0
        self.left_cycle_idx = 0
        self.right_cycle_idx = 0
        self.back_toggle = False
        self.honk_until = 0

        # --- HUD (now part of the game world) ---
        self.txt_level = ft.Text()
        # UI FIX: Split speed text into two lines to prevent overflow
        self.txt_speed_line1 = ft.Text()
        self.txt_speed_line2 = ft.Text()
        self.txt_score = ft.Text()
        self.hearts_row = ft.Row(spacing=4)
        self.btn_mute = ft.IconButton(
            icon=ft.Icons.VOLUME_UP, tooltip="Mute/Unmute (M)",
            on_click=lambda e: self.toggle_mute()
        )
        
        # UI FIX: Create a Column for the new speed text
        speed_col = ft.Column(
            [self.txt_speed_line1, self.txt_speed_line2],
            spacing=0
        )
        
        self.hud = ft.Container(
            content=ft.Row(
                [
                    self.txt_level, 
                    ft.Container(width=10), 
                    speed_col, # Use the new Column here
                    ft.Container(expand=True), 
                    self.btn_mute,
                    ft.Container(width=12), 
                    self.txt_score, 
                    ft.Container(width=12), 
                    self.hearts_row
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            # Position and width will be set in _recalc_layout
            top=0, left=0, 
        )

        # --- Overlays (messages) ---
        self.death_msg = ft.Text() 
        
        self.death_msg_cont = ft.Container(
            content=self.death_msg,
            alignment=ft.alignment.center_left, # Aligned left, on the bottom grass
            padding=ft.padding.only(left=20),
            visible=False # This container controls visibility
        )
        
        self.center_prompt = ft.Text()
        self.center_prompt_cont = ft.Container(
            content=self.center_prompt,
            alignment=ft.alignment.center,
            visible=False
        )
        
        self.level_banner = ft.Text()
        self.level_banner_cont = ft.Container(
            content=self.level_banner,
            alignment=ft.alignment.center,
            visible=False
        )
        
        self.banner_ticks = 0
        self.btn_restart_cp = ft.ElevatedButton(
            "Restart (checkpoint)",
            on_click=lambda e: self.restart_from_checkpoint(),
            bgcolor="#22c55e", color="#0b1014", visible=False
        )
        self.btn_restart_cont = ft.Container(
            content=self.btn_restart_cp, 
            alignment=ft.alignment.center
        )

        # D-pad (created responsively)
        self.dpad = None

        # world
        self.cars: list[Car] = []
        self.stains: list[BloodStain] = []

        self.canvas = cv.Canvas(shapes=[])
        
        self.world = ft.Stack(
            controls=[
                self.canvas,
                self.player, 
                self.hud, # HUD is here now
                self.death_msg_cont, 
                self.center_prompt_cont, 
                self.level_banner_cont,  
                self.btn_restart_cont,
                # dpad will be inserted after layout calculation
            ]
        )

        # CHANGE: self.root now centers a new world_container
        self.world_container = ft.Container(
            content=self.world, 
            alignment=ft.alignment.center
        )
        self.root = ft.Column(
            [self.world_container], 
            spacing=0, 
            expand=True, 
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.p.add(self.root)
        self.p.update()

        # initial layout (after update, width/height are known)
        self._recalc_layout(initial=True, size=(self.p.width or 800, self.p.height or 600))
        self.reset_player(); self.create_cars(); self.update_hud(); self.p.update()
        self.show_level_banner()
        self.redraw_canvas()

    # ---- RESPONSIVENESS ----
    def _on_resize(self, e: ft.ControlEvent):
        # e.width, e.height are the *entire* page dimensions
        self._recalc_layout(size=(e.width, e.height))

    def _recalc_layout(self, initial=False, size: tuple[int, int] | None = None):
        """Fit W,H,GRID, etc., to the screen size; rescale elements."""
        global W, H, GRID, PLAYER_SIZE, START_X, START_Y, LANES_Y, MIN_GAP

        oldW, oldGRID = W, GRID

        if size is not None:
            win_w, win_h = size
        else:
            win_w = self.p.width or 800
            win_h = self.p.height or 600

        appbar_h = 56 
        avail_w = int(win_w)
        avail_h = max(240, int(win_h - appbar_h))

        # CHANGE: Implement 4:3 Aspect Ratio (20x15 grid)
        grid_from_width = avail_w / 20.0
        grid_from_height = avail_h / 15.0
        
        # SCALING FIX: Use min 16px, otherwise GRID can be too small
        GRID = max(16, int(min(grid_from_width, grid_from_height)))
        
        W = 20 * GRID
        H = 15 * GRID
        # --- End Aspect Ratio Logic ---
        
        PLAYER_SIZE = GRID
        
        # GAMEPLAY FIX: Update MIN_GAP based on new GRID
        MIN_GAP = int(GRID * 1.5)
        
        START_X = (W // (GRID * 2)) * GRID 
        START_Y = GRID * 13
        LANES_Y = [GRID * 4, GRID * 6, GRID * 8, GRID * 10]
        
        # Font sizes / UI
        # UI FIX: Reduced font sizes to be more responsive
        base_txt = max(12, int(GRID * 0.60)) # Było 0.80
        speed_txt_size = max(10, int(GRID * 0.45)) # New size for speed text
        
        self.txt_level.size = base_txt
        self.txt_speed_line1.size = speed_txt_size
        self.txt_speed_line2.size = speed_txt_size
        self.txt_score.size = base_txt
        
        self.death_msg.size = max(20, int(GRID * 1.0)) # Było 1.20
        self.center_prompt.size = max(12, int(GRID * 0.40)) # Było 0.45
        self.level_banner.size = max(14, int(GRID * 0.50)) # Było 0.55

        # Colors
        self.txt_level.color = "#000000"
        self.txt_speed_line1.color = "#000000"
        self.txt_speed_line2.color = "#000000"
        self.txt_score.color = "#000000"
        
        self.death_msg.color = "#ff453a"
        self.level_banner.color = "#ffd166"
        self.center_prompt.color = "#fff"

        # Set Canvas / World size
        self.canvas.width = W
        self.canvas.height = H
        self.world.width = W
        self.world.height = H
        
        # Set HUD to full width
        self.hud.width = W
        self.hud.padding = ft.padding.only(left=10, right=10, top=max(4, int(GRID * 0.2)))

        # Overlay positions dependent on W,H
        self.level_banner_cont.width = W
        self.level_banner_cont.top = GRID * 1.5 # Below HUD
        
        self.center_prompt_cont.width = W
        self.center_prompt_cont.top = H / 2 - int(GRID * 1.8)
        
        self.death_msg_cont.width = W
        self.death_msg_cont.top = GRID * 12.5 # On the bottom green grass

        # Restart Button
        self.btn_restart_cp.width = int(GRID * 6.5)
        self.btn_restart_cp.height = int(GRID * 1.0)
        self.btn_restart_cont.width = W
        self.btn_restart_cont.height = H # Fills background to center

        # CHANGE: Set the size of the centering container
        self.world_container.width = W
        self.world_container.height = H
        self.world_container.update()
        
        # D-pad: rebuild (remove old, add new)
        if self.dpad and self.dpad in self.world.controls:
            self.world.controls.remove(self.dpad)
        self.dpad = self._build_dpad_responsive()
        self.world.controls.append(self.dpad) # Add to the end (on top)
        self.world.update()

        # Rescale player (size + position to new grid)
        self.player.width = PLAYER_SIZE
        self.player.height = PLAYER_SIZE
        self.player_img.width = PLAYER_SIZE
        self.player_img.height = PLAYER_SIZE

        if not initial and oldGRID > 0 and oldW > 0:
            gx = round((self.player.left or START_X) / oldGRID)
            gy = round((self.player.top or START_Y) / oldGRID)
            self.player.left = max(0, min(W - PLAYER_SIZE, gx * GRID))
            self.player.top = max(0, min(H - PLAYER_SIZE, gy * GRID))
        else:
            self.player.left = START_X
            self.player.top = START_Y
        self.player.update()
        self.player_img.update()

        # Rescale cars
        if self.cars:
            sx = W / oldW if oldW else 1.0
            sg = GRID / oldGRID if oldGRID else 1.0
            for car in self.cars:
                car.x *= sx
                car_y_idx = round(car.y / (oldGRID or GRID))
                car.y = car_y_idx * GRID
                car.length *= sg

        self.redraw_canvas()
        self.update_hud()
        self.p.update()

    def _build_dpad_responsive(self):
        btn_size = int(GRID * 1.3)
        gap = max(4, int(GRID * 0.15))
        pad = max(8, int(GRID * 0.35))

        base_left = W - (btn_size * 3 + gap * 2) - pad
        base_top = H - (btn_size * 3 + gap * 2) - pad

        def btn(icon, dx, dy, left, top):
            return ft.Container(
                left=left, top=top, width=btn_size, height=btn_size,
                bgcolor=ft.Colors.with_opacity(0.15, "#ffffff"),
                border_radius=999,
                content=ft.IconButton(
                    icon=icon,
                    on_click=lambda e, dx=dx, dy=dy: self.p.run_task(self.move_player, dx, dy),
                    style=ft.ButtonStyle(shape=ft.CircleBorder()),
                    tooltip="Move",
                ),
                shadow=ft.BoxShadow(blur_radius=8, spread_radius=0, color=ft.Colors.with_opacity(0.25, "#000000"))
            )
        up    = btn(ft.Icons.KEYBOARD_ARROW_UP,    0, -1, base_left + btn_size + gap, base_top)
        leftb = btn(ft.Icons.KEYBOARD_ARROW_LEFT, -1,  0, base_left,                  base_top + btn_size + gap)
        rightb= btn(ft.Icons.KEYBOARD_ARROW_RIGHT, 1,  0, base_left + 2*btn_size + 2*gap, base_top + btn_size + gap)
        down  = btn(ft.Icons.KEYBOARD_ARROW_DOWN,  0,  1, base_left + btn_size + gap, base_top + 2*btn_size + 2*gap)

        cross = ft.Container(
            left=base_left, top=base_top,
            width=btn_size * 3 + gap * 2, height=btn_size * 3 + gap * 2,
            bgcolor=ft.Colors.with_opacity(0.05, "#ffffff"), border_radius=16
        )
        # Return a Stack to be added to self.world
        return ft.Stack(controls=[cross, up, leftb, rightb, down])

    # ---- AUDIO helpers ----
    def _pick_next_bgm(self):
        choices = [t for t in self._bgm_tracks if t != self._last_bgm] or self._bgm_tracks
        nxt = random.choice(choices); self._last_bgm = nxt; return nxt
    def _bgm_next(self):
        try:
            self.bgm.src = self._pick_next_bgm(); self.bgm.update(); self.bgm.play()
        except Exception as e:
            print(f"Error playing BGM: {e}")
    def toggle_mute(self):
        try:
            if self.bgm.volume > 0:
                self.bgm.volume = 0.0; self.btn_mute.icon = ft.Icons.VOLUME_OFF
            else:
                self.bgm.volume = 0.25; self.btn_mute.icon = ft.Icons.VOLUME_UP
            self.bgm.update(); self.btn_mute.update()
        except Exception as e:
            print(f"Error muting: {e}")

    # --- drawing cars ---
    def _car_shapes(self, c: Car):
        L, Ht, x, y = c.length, GRID, c.x, c.y
        dir_right = c.speed > 0
        if x + L < 0 or x > W: return []
        shapes = []
        shapes.append(RRECT(x, y, L, Ht, 8, paint=FILL(c.color)))
        roof_col = shade(c.color, 0.85 if hash((int(c.x), int(c.y))) % 2 == 0 else 1.12)
        roof_w, roof_h = L * 0.60, Ht * 0.40
        roof_left, roof_top = x + (L - roof_w)/2, y + (Ht - roof_h)/2
        shapes.append(RRECT(roof_left, roof_top, roof_w, roof_h, 6, paint=FILL(roof_col)))
        glass_color = "#111827"
        ring_stroke = max(6, int(Ht * 0.18))
        shapes.append(RRECT(roof_left, roof_top, roof_w, roof_h, min(12, Ht//2), paint=STROKE(glass_color, ring_stroke)))
        light_len, light_th = min(int(GRID * 0.45), max(10, int(L * 0.08))), max(3, int(GRID * 0.10))
        off_y1, off_y2 = int(y + Ht * 0.28), int(y + Ht * 0.68)
        if dir_right:
            front_x, back_x = int(x + L - light_len - 2), int(x + 2)
        else:
            front_x, back_x = int(x + 2), int(x + L - light_len - 2)
        shapes += [
            cv.Rect(front_x, off_y1, light_len, light_th, paint=FILL("#ffffff")),
            cv.Rect(front_x, off_y2, light_len, light_th, paint=FILL("#ffffff")),
            cv.Rect(back_x, off_y1, light_len, light_th, paint=FILL("#ff3b30")),
            cv.Rect(back_x, off_y2, light_len, light_th, paint=FILL("#ff3b30")),
        ]
        return shapes

    def redraw_canvas(self):
        shapes = [
            # Green zones and road
            cv.Rect(0, 0, W, GRID*3, paint=FILL("#2a9d8f")), # Top green
            cv.Rect(0, GRID*12, W, H-GRID*12, paint=FILL("#2a9d8f")), # Bottom green
            cv.Rect(0, GRID*3, W, GRID*9, paint=FILL("#1e1e1e")), # Road
            # Road edge lines
            cv.Rect(0, GRID*3, W, 2, paint=FILL("#f1f2f6")),
            cv.Rect(0, GRID*12, W, 2, paint=FILL("#f1f2f6")),
        ]
        # Lane markings
        for y in (LANES_Y[1], LANES_Y[2], LANES_Y[3]):
            # Ensure W and GRID are integers for range()
            for x in range(0, W, GRID):
                shapes.append(cv.Rect(x, y-4, GRID//2, max(2, GRID//20), paint=FILL("#f1f2f6")))
        # Cars
        for c in self.cars: shapes += self._car_shapes(c)
        # Blood stains
        for s in self.stains:
            r = s.t / s.max_t
            # New logic for scaling and alpha
            if r < 0.3: # First 30% time - fast expansion
                size = 10 + int(90 * (r / 0.3))
                alpha = 0.9 * (r / 0.3)
            elif r > 0.7: # Last 30% time - fast fade out
                k = (r - 0.7) / 0.3
                size = max(1, int(100 * (1 - k)))
                alpha = max(0, 0.9 * (1 - k))
            else: # Middle phase - full size, constant alpha
                size = 100
                alpha = 0.9

            if size > 0:
                shapes.append(cv.Circle(s.x, s.y, size/2, paint=FILL(ft.Colors.with_opacity(alpha, "#8b0000"))))
        
        self.canvas.shapes = shapes
        self.canvas.update()

    # --- speeds ---
    def speed_multiplier_for_level(self, lvl:int)->float:
        mult, last = self.START_MULT, 1
        for up, k in self.SPEED_SEGMENTS:
            if lvl <= last: break
            take = min(lvl, up) - last
            if take > 0: mult += (k * self.BASE_STEP) * take
            last = up
        if lvl > last: mult += (200 * self.BASE_STEP) * (lvl - last)
        return mult

    # --- cars ---
    def destroy_cars(self): self.cars.clear()
    def create_cars(self):
        self.cars.clear()
        specs = [
            (LANES_Y[0],  3.0, 3, 2.0*GRID),
            (LANES_Y[1],  2.2, 3, 2.5*GRID),
            (LANES_Y[2], -2.6, 2, 1.5*GRID),
            (LANES_Y[3], -1.8, 4, 2.0*GRID),
        ]
        colors = ["#ef476f", "#ffd166", "#06d6a0", "#118ab2", "#f78c6b", "#9b5de5"]
        scale = self.speed_multiplier_for_level(self.level)
        for y, base, count, L in specs:
            
            # GAMEPLAY FIX: Reduce car count in portrait mode
            base_count = count
            responsive_count = base_count
            if W < H: # Portrait mode
                responsive_count = max(1, int(base_count * 0.7)) # 30% reduction
            
            spd, dir_right = base * scale, base * scale > 0
            edge = (-L - random.randint(50, 200)) if dir_right else (W + random.randint(50, 200))
            
            # Use responsive_count instead of count
            pos = [edge - i*(L+MIN_GAP) if dir_right else edge + i*(L+MIN_GAP) for i in range(responsive_count)]
            
            for x in pos:
                self.cars.append(Car(y, spd, L, random.choice(colors), x))
        self.redraw_canvas()

    # --- HUD / banners ---
    def _kmh(self, lvl:int)->float: return 5.0 * lvl
    def update_hud(self):
        cur, nxt = self.speed_multiplier_for_level(self.level), self.speed_multiplier_for_level(min(self.level+1, MAX_LEVEL))
        self.txt_level.value = f"LVL: {self.level}/{MAX_LEVEL}"
        
        # UI FIX: Update the two new text lines for speed
        self.txt_speed_line1.value = f"Speed x{cur:.2f} → x{nxt:.2f}"
        self.txt_speed_line2.value = f"{self._kmh(self.level):.0f}→{self._kmh(min(self.level+1, MAX_LEVEL)):.0f} km/h"
        
        self.txt_score.value = f"SCORE: {self.score}"
        blink = (self.tick // 6) % 2 == 0
        
        # UI FIX: Reduced heart size to be more responsive
        self.hearts_row.controls = [
            ft.Text(("❤" if (i < self.lives and not (self.lives == 1 and i == 0 and not blink)) else "♡"),
                    color=(HEART_RED if i < self.lives else HEART_WHITE), size=max(14, int(GRID*0.45))) # Było 18, 0.55
            for i in range(4)
        ]
        self.btn_restart_cp.visible = self.game_over
        
        # Update HUD and restart button
        self.hud.update()
        self.btn_restart_cont.update()


    def show_level_banner(self):
        self.level_banner.value = f"LEVEL {self.level}"
        self.level_banner_cont.visible = True
        self.banner_ticks = 0
        self.level_banner_cont.update()

    # --- player & input ---
    def reset_player(self):
        self.player.left, self.player.top = START_X, START_Y
        self.player.width = PLAYER_SIZE; self.player.height = PLAYER_SIZE
        self.player_img.width = PLAYER_SIZE; self.player_img.height = PLAYER_SIZE
        self.player.data = {"alive": True}; self.player.update()
        self.player_img.src = self.SPRITES["START"]; self.player_img.update()
        self.current_dir = "front"; self.move_anim_until = 0
        self.last_move_tick = self.tick

    async def move_player(self, dx, dy):
        if not self.player.data.get("alive", True): return
        old_left, old_top = self.player.left, self.player.top
        self.player.left = max(0, min(W - PLAYER_SIZE, (self.player.left or 0) + dx * GRID))
        self.player.top  = max(0, min(H - PLAYER_SIZE, (self.player.top  or 0) + dy * GRID))
        self.player.update()
        moved = (self.player.left != old_left or self.player.top != old_top)
        if moved:
            self._play_sfx("step")
            if dx > 0: self.current_dir = "right"
            elif dx < 0: self.current_dir = "left"
            elif dy < 0: self.current_dir = "front"
            elif dy > 0: self.current_dir = "back"
            self.move_anim_until = self.tick + 6
            self.last_move_tick = self.tick

    def _anim_update(self):
        if self.tick < self.honk_until:
            if self.player_img.src != self.SPRITES["FUCK"]:
                self.player_img.src = self.SPRITES["FUCK"]; self.player_img.update()
            return

        idle_ticks = self.tick - self.last_move_tick
        if idle_ticks >= IDLE_RANDOM_AFTER:
            if (self.anim_tick_acc % ANIM_DT_TICKS) == 0:
                self.player_img.src = random.choice(self.ALL_SPRITES_FOR_IDLE)
                self.player_img.update()
            self.anim_tick_acc += 1
            return

        if self.tick < self.move_anim_until:
            if (self.anim_tick_acc % ANIM_DT_TICKS) == 0:
                if self.current_dir == "front":
                    self.player_img.src = self.SPRITES["STEP_FRONT"][self.step_front_idx]
                    self.player_img.update(); self.step_front_idx = (self.step_front_idx + 1) % 3
                elif self.current_dir == "back":
                    self.player_img.src = self.SPRITES["STEP_BACK"] if self.back_toggle else self.SPRITES["LOOK_BACK"]
                    self.player_img.update(); self.back_toggle = not self.back_toggle
                elif self.current_dir == "left":
                    seq = [self.SPRITES["LOOK_LEFT"]] + self.SPRITES["STEP_FRONT"]
                    self.player_img.src = seq[self.left_cycle_idx % len(seq)]
                    self.player_img.update(); self.left_cycle_idx += 1
                elif self.current_dir == "right":
                    seq = [self.SPRITES["LOOK_RIGHT"]] + self.SPRITES["STEP_FRONT"]
                    self.player_img.src = seq[self.right_cycle_idx % len(seq)]
                    self.player_img.update(); self.right_cycle_idx += 1
            self.anim_tick_acc += 1
            return

        if self.player_img.src != self.SPRITES["START"]:
            self.player_img.src = self.SPRITES["START"]; self.player_img.update()

    def on_key(self, e: ft.KeyboardEvent):
        m = {"ArrowRight":(1,0),"d":(1,0),"D":(1,0),
             "ArrowLeft":(-1,0),"a":(-1,0),"A":(-1,0),
             "ArrowUp":(0,-1),"w":(0,-1),"W":(0,-1),
             "ArrowDown":(0,1),"s":(0,1),"S":(0,1)}
        if e.key == " " and self.game_over:
            self.restart_from_checkpoint(); return
        if e.key in ("m", "M"):
            self.toggle_mute(); return
        dxdy = m.get(e.key)
        if dxdy: self.p.run_task(self.move_player, *dxdy)

    # --- game events ---
    def player_die(self):
        if not self.player.data.get("alive", True): return
        self._play_sfx("hit")
        self.player.data["alive"] = False; self.lives -= 1
        self.stains.append(BloodStain((self.player.left or 0) + PLAYER_SIZE/2, (self.player.top or 0) + PLAYER_SIZE/2))
        self.death_msg.value = random.choice(["AW, MAN!","WHAT A NOOB!","OMG YOU ROOKIE!","NICE GOING, GOOFBALL","ROAD HUGGER!","SPLAT!"])
        
        self.death_msg_cont.visible = True
        self.death_msg_cont.update()
        
        if self.lives <= 0 and not self.game_over:
            self.game_over = True
            self.center_prompt.value = "GAME OVER — Space / Restart (checkpoint)"
            self.center_prompt_cont.visible = True
            self.center_prompt_cont.update()
        self.update_hud()

    def level_complete(self):
        self._play_sfx("level")
        prev = self.level; self.score += self.level * 100; self.level = min(MAX_LEVEL, self.level + 1)
        if prev % 10 == 0: self.checkpoint_level, self.checkpoint_score = self.level, self.score
        
        self.center_prompt.value = f"LEVEL UP! → {self.level}"
        self.center_prompt_cont.visible = True
        self.center_prompt_cont.update()
        
        self.show_level_banner()
        self.reset_player(); self.destroy_cars(); self.create_cars(); self.update_hud()

    def restart_from_checkpoint(self):
        self.level, self.score, self.lives, self.game_over = self.checkpoint_level, self.checkpoint_score, 4, False
        self.death_msg_cont.visible = False 
        self.center_prompt_cont.visible = False
        self.death_msg_cont.update() 
        self.center_prompt_cont.update()
        
        self.destroy_cars(); self.stains.clear()
        self.reset_player(); self.create_cars(); self.update_hud()
        self.show_level_banner()
        
        # AUDIO FIX: Force BGM to restart
        try:
            self.bgm.play()
        except Exception as e:
            print(f"Error restarting BGM: {e}")
            
        self.redraw_canvas()

    def exit_game(self):
        ok = False
        for attr in ("window_close", "window_destroy"):
            try:
                if hasattr(self.p, attr):
                    getattr(self.p, attr)(); ok = True; break
            except Exception:
                pass
        if not ok:
            # This is expected behavior on mobile
            self.center_prompt.value = "Cannot close window automatically. Please close the app using system navigation."
            self.center_prompt_cont.top = GRID
            self.center_prompt_cont.visible = True
            self.center_prompt_cont.update()

    # --- spacing enforcement ---
    def _enforce_spacing(self):
        lanes = defaultdict(list)
        for c in self.cars: lanes[(c.y, 1 if c.speed > 0 else -1)].append(c)
        for (y, d), Ls in lanes.items():
            Ls.sort(key=lambda c: c.x, reverse=(d < 0))
            for i in range(1, len(Ls)):
                a, b = Ls[i-1], Ls[i]
                if d > 0:
                    need = a.x + a.length + MIN_GAP
                    if b.x < need: b.x = need
                else:
                    need = a.x - b.length - MIN_GAP
                    if b.x > need: b.x = need

    # --- main loop ---
    async def loop(self):
        level_up_cooldown = 0
        while True:
            self.tick += 1

            for s in self.stains: s.step()
            self.stains = [s for s in self.stains if s.alive()]
            
            if self.death_msg_cont.visible and self.tick % 40 == 0:
                self.death_msg_cont.visible = False; self.death_msg_cont.update()
                
            if self.center_prompt_cont.visible and level_up_cooldown > 20:
                self.center_prompt_cont.visible = False; self.center_prompt_cont.update()
            if self.level_banner_cont.visible:
                self.banner_ticks += 1
                if self.banner_ticks > 60:
                    self.level_banner_cont.visible = False; self.level_banner_cont.update()

            if not self.game_over:
                for car in self.cars:
                    car.x += car.speed
                    if car.speed > 0 and car.x > W: car.x = -car.length - random.randint(50, 200)
                    if car.speed < 0 and car.x + car.length < 0: car.x = W + random.randint(50, 200)

                    if car.honk_timer > 0: car.honk_timer -= 1
                    if self.player.data.get("alive", True) and car.honk_timer == 0 and car.is_near(self.player.left or 0, self.player.top or 0):
                        self._play_sfx("honk")
                        car.honk_timer = 18
                        self.honk_until = self.tick + HONK_REACT_TICKS

                    if self.player.data.get("alive", True) and car.collides(self.player.left or 0, self.player.top or 0):
                        self.player_die()

                self._enforce_spacing()

                if not self.player.data.get("alive", True) and self.tick % 30 == 0 and self.lives > 0:
                    self.reset_player()
                if self.player.data.get("alive", True) and (self.player.top or 0) <= GRID * 3:
                    self.level_complete(); level_up_cooldown = 0

            self._anim_update()

            self.redraw_canvas()
            self.update_hud()
            level_up_cooldown += 1
            await asyncio.sleep(FPS_SLEEP)

# --- run ---
async def main(page: ft.Page):
    page.bgcolor = "#0d1117"
    game = GonzoGame(page)
    page.run_task(game.loop)

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")

