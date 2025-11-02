import flet as ft
import asyncio
import random

W, H = 800, 600
GRID_SIZE = 40

async def main(page: ft.Page):
    page.title = "Gonzo on Motorway (Flet Edition)"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER

    player = ft.Container(
        width=GRID_SIZE,
        height=GRID_SIZE,
        bgcolor="blue",
        left=GRID_SIZE * 5,
        top=GRID_SIZE * 10,
    )

    cars = []
    stack = ft.Stack(width=W, height=H, controls=[player])
    page.add(stack)

    async def move_player(dx, dy):
        player.left = max(0, min(W - GRID_SIZE, player.left + dx * GRID_SIZE))
        player.top = max(0, min(H - GRID_SIZE, player.top + dy * GRID_SIZE))
        player.update()

    async def add_car(y):
        car = ft.Container(
            width=GRID_SIZE * 2,
            height=GRID_SIZE,
            bgcolor="red",
            left=W,
            top=y,
        )
        stack.controls.append(car)
        stack.update()
        cars.append(car)

    async def game_loop():
        while True:
            for car in cars:
                car.left -= 5
                if car.left < -GRID_SIZE:
                    car.left = W
                car.update()
            await asyncio.sleep(0.05)

    # obsługa klawiatury
    def on_key(e: ft.KeyboardEvent):
        dx, dy = 0, 0
        if e.key == "ArrowRight": dx = 1
        elif e.key == "ArrowLeft": dx = -1
        elif e.key == "ArrowUp": dy = -1
        elif e.key == "ArrowDown": dy = 1
        asyncio.create_task(move_player(dx, dy))

    page.on_keyboard_event = on_key

    await add_car(GRID_SIZE * 4)
    await add_car(GRID_SIZE * 6)
    await game_loop()

ft.app(target=main)
