import flet as ft, asyncio, random
from flet import canvas as cv
from dataclasses import dataclass
from collections import defaultdict

# ---- Audio migration: use flet-audio if available (no deprecation warnings) ----
try:
    from flet_audio import Audio as FAudio
    AudioCtrl = FAudio           # new Audio control
except Exception:
    AudioCtrl = ft.Audio         # fallback to deprecated ft.Audio (still works)

# --- Config (start; will be recomputed on resize) ---
W, H, GRID = 800, 600, 40
LANES_Y = [GRID * 4, GRID * 6, GRID * 8, GRID * 10]
START_X, START_Y, PLAYER_SIZE = GRID * 5, GRID * 13, GRID
FPS_SLEEP, MAX_LEVEL, MIN_GAP = 0.05, 60, int(GRID * 0.75)
HEART_RED, HEART_WHITE = "#ff3b30", "#ffffff"

ANIM_DT_TICKS = 2         # 0.1 s przy FPS_SLEEP=0.05
HONK_REACT_TICKS = 10     # 0.5 s
IDLE_RANDOM_AFTER = 100   # 5.0 s bez ruchu

def rects_intersect(ax, ay, aw, ah, bx, by, bw, bh):
    return (ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by)

# --- kolory / cienie ---
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
    return cv.Rect(x, y, w, h, paint=paint)

@dataclass
class BloodStain:
    x: float; y: float; t: int = 0; max_t: int = 60
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

    # --- pliki sprite'ów ---
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

        # Reakcja na zmianę rozmiaru (telefon/rotacja)
        self.p.on_resize = self._on_resize

        self.p.appbar = ft.AppBar(
            title=ft.Text("Gonzo on Motorway"),
            center_title=False,
            bgcolor=ft.Colors.with_opacity(0.05, "#ffffff"),
            actions=[ft.TextButton("Zamknij", on_click=lambda e: self.exit_game())],
        )

        # --- AUDIO ---
        self._sfx_pool_idx = {"honk": 0, "step": 0}
        self.sfx = {
            "hit":   [AudioCtrl(src="assets/hit.wav", volume=1.0)],
            "level": [AudioCtrl(src="assets/level.wav", volume=1.0)],
            "honk":  [AudioCtrl(src="assets/honk.wav", volume=0.5) for _ in range(3)],
            "step":  [AudioCtrl(src="assets/step.wav", volume=0.35) for _ in range(2)],
        }
        # nowe pliki tła: audio01.wav ... audio08.wav
        self._bgm_tracks = [f"assets/audio{str(i).zfill(2)}.wav" for i in range(1, 9)]
        self._last_bgm = None
        self.bgm = AudioCtrl(src=self._pick_next_bgm(), volume=0.25, autoplay=True)
        self.bgm.on_ended = lambda e: self._bgm_next()
        for lst in self.sfx.values():
            for a in lst:
                self.p.overlay.append(a)
        self.p.overlay.append(self.bgm)
        self.p.update()

        def _play_sfx(key: str):
            if key not in self.sfx: return
            if key in ("honk", "step"):
                i = self._sfx_pool_idx[key]
                a = self.sfx[key][i]
                self._sfx_pool_idx[key] = (i + 1) % len(self.sfx[key])
                a.play()
            else:
                self.sfx[key][0].play()
        self._play_sfx = _play_sfx

        # --- state ---
        self.level = 1; self.score = 0; self.lives = 4; self.game_over = False; self.tick = 0
        self.checkpoint_level = 1; self.checkpoint_score = 0

        # --- PLAYER: Image w Containerze (skalowane) ---
        self.player_img = ft.Image(src=self.SPRITES["START"], fit=ft.ImageFit.CONTAIN)
        self.player = ft.Container(content=self.player_img)

        # animacja sprita
        self.anim_tick_acc = 0
        self.last_move_tick = 0
        self.move_anim_until = 0
        self.current_dir = "front"
        self.step_front_idx = 0
        self.left_cycle_idx = 0
        self.right_cycle_idx = 0
        self.back_toggle = False
        self.honk_until = 0

        # HUD (rozmiary ustawiane responsywnie)
        self.txt_level = ft.Text()
        self.txt_speed = ft.Text()
        self.txt_score = ft.Text()
        self.hearts_row = ft.Row(spacing=4)
        self.btn_mute = ft.IconButton(
            icon=ft.Icons.VOLUME_UP, tooltip="Mute/Unmute (M)",
            on_click=lambda e: self.toggle_mute()
        )
        self.hud = ft.Container(
            content=ft.Row(
                [self.txt_level, ft.Container(width=10), self.txt_speed,
                 ft.Container(expand=True), self.btn_mute,
                 ft.Container(width=12), self.txt_score, ft.Container(width=12), self.hearts_row],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            )
        )

        # overlays
        self.death_msg = ft.Text(visible=False)
        self.center_prompt = ft.Text(visible=False)
        self.level_banner = ft.Text(visible=False)
        self.banner_ticks = 0
        self.btn_restart_cp = ft.ElevatedButton(
            "Restart (checkpoint)",
            on_click=lambda e: self.restart_from_checkpoint(),
            bgcolor="#22c55e", color="#0b1014", visible=False
        )

        # D-pad (tworzony responsywnie)
        self.dpad = None

        # świat
        self.cars: list[Car] = []
        self.stains: list[BloodStain] = []

        self.canvas = cv.Canvas(shapes=[])
        self.world = ft.Stack(
            controls=[
                self.canvas,
                self.player, self.death_msg, self.center_prompt, self.level_banner,
                # dpad wstawiany po przeliczeniu layoutu,
                ft.Container(content=self.btn_restart_cp, alignment=ft.alignment.center),
            ]
        )

        self.root = ft.Column([self.hud, ft.Container(content=self.world, expand=True)], spacing=0, expand=True)
        self.p.add(self.root)
        self.p.update()

        # inicjalny layout (po update width/height są już znane)
        self._recalc_layout(initial=True, size=(self.p.width or 800, self.p.height or 600))
        self.reset_player(); self.create_cars(); self.update_hud(); self.p.update()
        self.show_level_banner()
        self.redraw_canvas()

    # ---- RESPONSYWNOŚĆ ----
    def _on_resize(self, e: ft.ControlEvent):
        # e.width, e.height – aktualne wymiary strony
        self._recalc_layout(size=(e.width, e.height))

    def _recalc_layout(self, initial=False, size: tuple[int, int] | None = None):
        """Dopasuj W,H,GRID itd. do rozmiaru ekranu; przeskaluj elementy."""
        global W, H, GRID, PLAYER_SIZE, START_X, START_Y, LANES_Y, MIN_GAP

        oldW, oldGRID = W, GRID

        if size is not None:
            win_w, win_h = size
        else:
            win_w = self.p.width or 800
            win_h = self.p.height or 600

        # Szacunkowa wysokość HUD
        hud_h = max(56, int(win_h * 0.08))
        self.hud.padding = 10
        self.hud.update()

        # Obszar dla świata
        avail_w = win_w
        avail_h = max(240, win_h - hud_h)

        # Proporcje 4:3
        target_ratio = 4 / 3
        world_w = min(avail_w, int(avail_h * target_ratio))
        world_h = int(world_w / target_ratio)

        # Nowy GRID
        W, H = world_w, world_h
        GRID = max(24, int(H / 15))   # min 24 px, by UI nie było za małe
        PLAYER_SIZE = GRID
        START_X, START_Y = GRID * 5, GRID * 13
        LANES_Y = [GRID * 4, GRID * 6, GRID * 8, GRID * 10]
        MIN_GAP = int(GRID * 0.75)

        # Rozmiary czcionek / UI
        base_txt = max(12, int(GRID * 0.40))
        self.txt_level.size = base_txt
        self.txt_speed.size = base_txt
        self.txt_score.size = base_txt
        self.death_msg.size = max(14, int(GRID * 0.45))
        self.center_prompt.size = max(14, int(GRID * 0.45))
        self.level_banner.size = max(16, int(GRID * 0.55))

        # Kolory
        self.txt_level.color = "#fff"
        self.txt_speed.color = "#a3e635"
        self.txt_score.color = "#fff"
        self.death_msg.color = "#ff453a"
        self.level_banner.color = "#ffd166"
        self.center_prompt.color = "#fff"

        # Ustaw rozmiar Canvas / World
        self.canvas.width = W
        self.canvas.height = H
        self.world.width = W
        self.world.height = H

        # Pozycje overlayów zależne od W,H
        self.level_banner.left = W / 2 - 80
        self.level_banner.top = GRID - 6

        self.center_prompt.left = max(8, W / 2 - 210)
        self.center_prompt.top = H / 2 - int(GRID * 1.8)

        # Przyciski Restart
        self.btn_restart_cp.width = int(GRID * 6.5)
        self.btn_restart_cp.height = int(GRID * 1.0)

        # D-pad: przebuduj (usuń stary, wstaw nowy)
        if self.dpad and self.dpad in self.world.controls:
            self.world.controls.remove(self.dpad)
        self.dpad = self._build_dpad_responsive()
        self.world.controls.insert(5, self.dpad)  # przed kontenerem restartu
        self.world.update()

        # Skalowanie gracza (rozmiar + pozycja do nowej siatki)
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

        # Skalowanie aut
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
        return ft.Stack(controls=[cross, up, leftb, rightb, down])

    # ---- AUDIO helpers ----
    def _pick_next_bgm(self):
        choices = [t for t in self._bgm_tracks if t != self._last_bgm] or self._bgm_tracks
        nxt = random.choice(choices); self._last_bgm = nxt; return nxt
    def _bgm_next(self):
        self.bgm.src = self._pick_next_bgm(); self.bgm.update(); self.bgm.play()
    def toggle_mute(self):
        if self.bgm.volume > 0:
            self.bgm.volume = 0.0; self.btn_mute.icon = ft.Icons.VOLUME_OFF
        else:
            self.bgm.volume = 0.25; self.btn_mute.icon = ft.Icons.VOLUME_UP
        self.bgm.update(); self.btn_mute.update()

    # --- rysowanie aut ---
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
            cv.Rect(0, 0, W, GRID*3, paint=FILL("#2a9d8f")),
            cv.Rect(0, GRID*12, W, H-GRID*12, paint=FILL("#2a9d8f")),
            cv.Rect(0, GRID*3, W, GRID*9, paint=FILL("#1e1e1e")),
            cv.Rect(0, GRID*3, W, 2, paint=FILL("#f1f2f6")),
            cv.Rect(0, GRID*12, W, 2, paint=FILL("#f1f2f6")),
        ]
        for y in (LANES_Y[1], LANES_Y[2], LANES_Y[3]):
            for x in range(0, W, GRID):
                shapes.append(cv.Rect(x, y-4, GRID//2, max(2, GRID//20), paint=FILL("#f1f2f6")))
        for c in self.cars: shapes += self._car_shapes(c)
        for s in self.stains:
            r = s.t / s.max_t
            if r < .25:
                size = 10 + int(90 * (r / .25)); alpha = .9
            elif r >= .75:
                k = (r - .75) / .25; size = int(100 * (1 - k)); alpha = max(0, .9 * (1 - k))
            else:
                size = 100; alpha = .9
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
            spd, dir_right = base * scale, base * scale > 0
            edge = (-L - random.randint(50, 200)) if dir_right else (W + random.randint(50, 200))
            pos = [edge - i*(L+MIN_GAP) if dir_right else edge + i*(L+MIN_GAP) for i in range(count)]
            for x in pos:
                self.cars.append(Car(y, spd, L, random.choice(colors), x))
        self.redraw_canvas()

    # --- HUD / banners ---
    def _kmh(self, lvl:int)->float: return 5.0 * lvl
    def update_hud(self):
        cur, nxt = self.speed_multiplier_for_level(self.level), self.speed_multiplier_for_level(min(self.level+1, MAX_LEVEL))
        self.txt_level.value = f"LVL: {self.level}/{MAX_LEVEL}"
        self.txt_speed.value = f"speed x{cur:.2f} → x{nxt:.2f}  —  {self._kmh(self.level):.0f}→{self._kmh(min(self.level+1, MAX_LEVEL)):.0f} km/h"
        self.txt_score.value = f"SCORE: {self.score}"
        blink = (self.tick // 6) % 2 == 0
        self.hearts_row.controls = [
            ft.Text(("❤" if (i < self.lives and not (self.lives == 1 and i == 0 and not blink)) else "♡"),
                    color=(HEART_RED if i < self.lives else HEART_WHITE), size=max(18, int(GRID*0.55)))
            for i in range(4)
        ]
        self.btn_restart_cp.visible = self.game_over
        self.hearts_row.update(); self.txt_level.update(); self.txt_speed.update(); self.txt_score.update()
        self.btn_restart_cp.update(); self.btn_mute.update()

    def show_level_banner(self):
        self.level_banner.value = f"LEVEL {self.level}"
        self.level_banner.visible = True
        self.banner_ticks = 0
        self.level_banner.update()

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
        self.death_msg.value = random.choice(["ECH TY CIULU","CO ZA JEŁOP","OMG TY NUBKU!!!","CO ZA BĘCWAŁ","KTO CIĘ UCZYŁ ŁAZIĆ","JAKI BARANEK","TY, GUZA SZUKASZ?"])
        self.death_msg.left, self.death_msg.top, self.death_msg.visible = (self.player.left or 0) - 10, (self.player.top or 0) - 26, True
        self.death_msg.update()
        if self.lives <= 0 and not self.game_over:
            self.game_over = True
            self.center_prompt.value, self.center_prompt.left = "GAME OVER — Space / Restart (checkpoint)", max(8, W/2 - 210)
            self.center_prompt.top, self.center_prompt.visible = H/2 - int(GRID*1.8), True
            self.center_prompt.update()
        self.update_hud()

    def level_complete(self):
        self._play_sfx("level")
        prev = self.level; self.score += self.level * 100; self.level = min(MAX_LEVEL, self.level + 1)
        if prev % 10 == 0: self.checkpoint_level, self.checkpoint_score = self.level, self.score
        self.center_prompt.value, self.center_prompt.left, self.center_prompt.top = f"LEVEL UP! → {self.level}", max(8, W/2 - 80), GRID
        self.center_prompt.visible = True; self.center_prompt.update()
        self.show_level_banner()
        self.reset_player(); self.destroy_cars(); self.create_cars(); self.update_hud()

    def restart_from_checkpoint(self):
        self.level, self.score, self.lives, self.game_over = self.checkpoint_level, self.checkpoint_score, 4, False
        self.death_msg.visible = self.center_prompt.visible = False
        self.destroy_cars(); self.stains.clear()
        self.reset_player(); self.create_cars(); self.update_hud()
        self.show_level_banner()
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
            self.center_prompt.value = "Nie mogę zamknąć okna automatycznie. Zamknij kartę/okno przeglądarki."
            self.center_prompt.left = max(8, W/2 - 260)
            self.center_prompt.top = GRID
            self.center_prompt.visible = True
            self.center_prompt.update()

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
            if self.death_msg.visible and self.tick % 40 == 0:
                self.death_msg.visible = False; self.death_msg.update()
            if self.center_prompt.visible and level_up_cooldown > 20:
                self.center_prompt.visible = False; self.center_prompt.update()
            if self.level_banner.visible:
                self.banner_ticks += 1
                if self.banner_ticks > 60:
                    self.level_banner.visible = False; self.level_banner.update()

            if not self.game_over:
                for car in self.cars:
                    car.x += car.speed
                    if car.speed > 0 and car.x > W: car.x = -car.length - random.randint(50, 200)
                    if car.speed < 0 and car.x + self.cars[0].length < 0:  # safeguard if list non-empty
                        pass
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
