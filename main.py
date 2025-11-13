import flet as ft
import random
import re
import os
# Wymagana biblioteka do "fuzzy matching"
from thefuzz import fuzz

# --- STAŁA: Folder z zasobami ---
ASSETS_DIR = "assets"


# --------------------

def parse_question_file(page: ft.Page, filename: str) -> list:
    """
    Wczytuje plik .txt z folderu ASSETS_DIR i parsuje go do formatu listy pytań.

    Implementuje "ogólną logikę" próbującą dwóch ścieżek:
    1. Oficjalnej (w folderze /assets)
    2. Awaryjnej (w folderze głównym /)
    """
    parsed_questions = []
    content = ""

    # Ścieżka 1: Poprawna ścieżka do zasobów (w folderze assets)
    path1 = os.path.join(ASSETS_DIR, filename)

    # Ścieżka 2: Ścieżka awaryjna (plik w katalogu głównym)
    path2 = filename

    try:
        if page.platform in ("android", "ios"):
            # Dla Mobile (APK), używamy page.open_asset
            try:
                print(f"Mobile: Próba ścieżki 1 (w assets): {path1}")
                with page.open_asset(path1, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"Mobile: Sukces na ścieżce 1.")
            except Exception:
                print(f"Mobile: Ścieżka 1 nie powiodła się. Próba ścieżki 2 (w root): {path2}")
                with page.open_asset(path2, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"Mobile: Sukces na ścieżce 2.")
        
        elif page.web:
            # Dla Web (przeglądarki), używamy standardowego open()
            
            # Logika z `main.yml` (`--assets .` i `/base/url/`) pakuje:
            # - folder `assets` do `/assets/`
            # - pliki .txt do `/` (katalog główny)
            
            # Dlatego path1 (assets) prawdopodobnie zawiedzie, a path2 (root) zadziała.
            
            # Ścieżka 1: Próba otwarcia z folderu assets (ścieżka WZGLĘDNA)
            path1_web = f"{ASSETS_DIR}/{filename}" # np. "assets/20.txt"
            
            # --- KLUCZOWA POPRAWKA TUTAJ ---
            # Ścieżka 2: Próba otwarcia z katalogu głównego (ścieżka WZGLĘDNA)
            # Poprzednio było f"/{filename}" (absolutna), co powodowało błąd Errno 44
            path2_web = filename # np. "20.txt"

            try:
                print(f"Web: Próba ścieżki 1 (w assets): {path1_web}")
                with open(path1_web, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"Web: Sukces na ścieżce 1.")
            except FileNotFoundError:
                print(f"Web: Ścieżka 1 nie powiodła się. Próba ścieżki 2 (w root): {path2_web}")
                with open(path2_web, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"Web: Sukces na ścieżce 2.")
        
        else:
            # Dla lokalnego PC
            try:
                print(f"PC: Próba ścieżki 1 (w assets): {path1}")
                with open(path1, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"PC: Sukces na ścieżce 1.")
            except FileNotFoundError:
                print(f"PC: Ścieżka 1 nie powiodła się. Próba ścieżki 2 (w root): {path2}")
                with open(path2, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"PC: Sukces na ścieżce 2.")

    except Exception as e:
        # Błąd ostateczny - jeśli obie ścieżki zawiodą
        print(f"KRYTYCZNY BŁĄD: Nie można otworzyć pliku ani na ścieżce 1, ani na 2. Ostatnia próba: {path2}. Platforma: {page.platform}, Web: {page.web}. Błąd: {e}")
        return []

    # Dalsze parsowanie pliku (bez zmian)
    question_blocks = re.split(r'\n(?=\d+\.)', content)

    for block in question_blocks:
        block = block.strip()
        if not block:
            continue

        match = re.match(
            r"^\d+\.\s(.*?)\n"
            r"prawid(?:l|ł)owa\s+odpowied(?:z|ź)\s*=\s*(.*?)\n"
            r"odpowied(?:z|ź)\s+abcd\s*=\s*A\s*=\s*(.*?), B\s*=\s*(.*?), C\s*=\s*(.*?), D\s*=\s*(.*?)$",
            block, re.DOTALL | re.IGNORECASE
        )

        if match:
            try:
                question = match.group(1).strip()
                correct = match.group(2).strip()
                answers = [
                    match.group(3).strip(),
                    match.group(4).strip(),
                    match.group(5).strip(),
                    match.group(6).strip(),
                ]
                parsed_questions.append({
                    "question": question,
                    "correct": correct,
                    "answers": answers
                })
            except Exception as e:
                print(f"Błąd parsowania bloku: {block[:50]}... Błąd: {e}")
                pass
        else:
            print(f"Blok nie pasuje do wzorca: {block[:50]}...")
            pass

    return parsed_questions


def normalize_answer(text: str) -> str:
    """
    Normalizuje odpowiedź.
    """
    text = str(text).lower().strip()
    diacritics = {
        'ó': 'o', 'ł': 'l', 'ż': 'z', 'ź': 'z', 'ć': 'c',
        'ń': 'n', 'ś': 's', 'ą': 'a', 'ę': 'e', 'ü': 'u'
    }
    for char, replacement in diacritics.items():
        text = text.replace(char, replacement)
    text = text.replace('u', 'o')
    text = "".join(text.split())
    return text


def main(page: ft.Page):
    page.title = "Awantura o Kasę - Singleplayer"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.window_width = 600
    page.window_height = 800
    page.theme_mode = ft.ThemeMode.LIGHT
    page.scroll = ft.ScrollMode.AUTO

    # --- Zmienne stanu gry ---
    game_state = {
        "money": 10000,
        "current_question_index": -1,
        "base_stake": 500,
        "abcd_unlocked": False,
        "main_pot": 0,
        "money_spent_on_hints": 0,
        "current_bid_amount": 0,
        "max_bid_per_round": 5000,
        "current_bonus_pot": 0,
        "active_question_set": [],
        "total_questions": 0,
        "set_name": ""
    }

    # --- Kontrolki Flet (Elementy UI) ---

    # --- WIDOK 1: EKRAN GRY ---
    txt_money = ft.Text(
        value=f"Twoja kasa: {game_state['money']} zł",
        size=16,
        weight=ft.FontWeight.BOLD,
        color="green_600"
    )

    txt_money_spent = ft.Text(
        value="Wydano: 0 zł",
        size=14,
        color="grey_700",
        text_align=ft.TextAlign.RIGHT
    )

    txt_question_counter = ft.Text(
        value="Pytanie 0 / 0 (Zestaw 00)",
        size=16,
        color="grey_700",
        text_align=ft.TextAlign.CENTER
    )

    txt_main_pot = ft.Text(
        value=f"AKTUALNA PULA: 0 zł",
        size=22,
        weight=ft.FontWeight.BOLD,
        color="purple_600",
        text_align=ft.TextAlign.CENTER
    )

    txt_bonus_pot = ft.Text(
        value="Bonus od banku: 0 zł",
        size=16,
        color="blue_600",
        text_align=ft.TextAlign.CENTER,
        visible=False
    )

    txt_question = ft.Text(
        value="Wciśnij 'Start', aby rozpocząć grę!",
        size=18,
        weight=ft.FontWeight.BOLD,
        text_align=ft.TextAlign.CENTER
    )

    txt_feedback = ft.Text(value="", size=16, text_align=ft.TextAlign.CENTER)

    # --- Kontrolki UI Odpowiedzi (grupowane) ---
    txt_answer_field = ft.TextField(
        label="Wpisz swoją odpowiedź...",
        width=400,
        text_align=ft.TextAlign.CENTER,
        capitalization=ft.TextCapitalization.SENTENCES
    )

    btn_submit_answer = ft.Button(
        text="Zatwierdź odpowiedź",
        icon="check",
        on_click=None,
        width=400,
    )

    answers_container = ft.Column(
        controls=[],
        spacing=10,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False
    )

    answer_ui_container = ft.Column(
        [
            txt_answer_field,
            btn_submit_answer,
            answers_container,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False
    )

    # --- Kontrolki UI Licytacji (grupowane) ---
    btn_bid_100 = ft.Button(
        text="Licytuj +100 zł (Suma: 0 zł)",
        icon="add",
        on_click=None,
        width=400,
    )

    btn_start_answering = ft.Button(
        text="Pokaż pytanie",
        icon="gavel",
        on_click=None,
        width=400,
    )

    bidding_container = ft.Column(
        [
            btn_bid_100,
            btn_start_answering,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False
    )

    # --- Kontrolki Podpowiedzi i Nawigacji ---
    btn_hint_5050 = ft.Button(
        text="Kup podpowiedź 50/50 (losowo 500-2500 zł)",
        icon="lightbulb_outline",
        on_click=None,
        width=400,
        disabled=True
    )

    btn_buy_abcd = ft.Button(
        text="Kup opcje ABCD (losowo 1000-3000 zł)",
        icon="view_list",
        on_click=None,
        width=400,
        disabled=True
    )

    btn_next = ft.Button(
        text="Następne pytanie",
        on_click=None,
        visible=False,
        width=400
    )

    btn_back_to_menu = ft.Button(
        text="Wróć do menu",
        icon="arrow_back",
        on_click=None,
        width=400,
        visible=False,
        color="red"
    )

    # --- Kontener GŁÓWNEGO WIDOKU GRY ---
    game_view = ft.Column(
        controls=[
            ft.Container(
                content=ft.Row(
                    [
                        txt_money,
                        txt_money_spent,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER
                ),
                padding=ft.padding.only(left=20, right=20, top=10, bottom=5)
            ),
            ft.Divider(height=1, color="grey_300"),

            ft.Container(
                content=txt_question_counter,
                alignment=ft.alignment.center,
                padding=ft.padding.only(top=10)
            ),

            ft.Container(
                content=txt_main_pot,
                alignment=ft.alignment.center,
                padding=ft.padding.only(top=10, bottom=5)
            ),

            ft.Container(
                content=txt_bonus_pot,
                alignment=ft.alignment.center,
                padding=ft.padding.only(bottom=5)
            ),

            # Poprawiony kontener (usunięty błąd składni)
            ft.Container(
                content=txt_question,
                alignment=ft.alignment.center,
                padding=ft.padding.only(left=20, right=20, top=10, bottom=10),
                height=100
            ),

            bidding_container,
            answer_ui_container,

            ft.Divider(height=20, color="transparent"),

            ft.Column(
                [
                    btn_hint_5050,
                    btn_buy_abcd,
                    btn_next,
                    txt_feedback,
                    btn_back_to_menu,
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            )
        ],
        visible=False
    )

    # --- WIDOK 2: EKRAN GŁÓWNY (MENU) ---

    main_menu_feedback = ft.Text(
        value="",
        color="red",
        visible=False,
        text_align=ft.TextAlign.CENTER
    )

    def create_menu_tile(index, bgcolor):
        filename = f"{index:02d}.txt"
        
        # Logika "na sztywno" - zakładamy, że pliki istnieją.
        return ft.Button(
            content=ft.Text(value=f"{index:02d}", size=12),
            tooltip=f"Zestaw {index:02d}",
            width=35,
            height=35,
            on_click=lambda e, f=filename: start_game_session(e, f),
            disabled=False,
            style=ft.ButtonStyle(
                bgcolor=bgcolor
            )
        )

    menu_tiles_standard = [create_menu_tile(i, "blue_grey_50") for i in range(1, 31)]
    menu_tiles_popkultura = [create_menu_tile(i, "deep_purple_50") for i in range(31, 41)]
    menu_tiles_popkultura_muzyka = [create_menu_tile(i, "amber_50") for i in range(41, 51)]

    main_menu_view = ft.Column(
        [
            ft.Text("Wybierz zestaw pytań:", size=24, weight=ft.FontWeight.BOLD),
            ft.Text(f"Zakładam, że pliki 01-50.txt istnieją."),
            main_menu_feedback,
            ft.Divider(height=20),
            ft.Row(menu_tiles_standard[0:10], alignment=ft.MainAxisAlignment.CENTER, wrap=True),
            ft.Row(menu_tiles_standard[10:20], alignment=ft.MainAxisAlignment.CENTER, wrap=True),
            ft.Row(menu_tiles_standard[20:30], alignment=ft.MainAxisAlignment.CENTER, wrap=True),

            ft.Divider(height=30),
            ft.Text("Pytania popkultura Boost:", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(height=20),
            ft.Row(menu_tiles_popkultura, alignment=ft.MainAxisAlignment.CENTER, wrap=True),

            ft.Divider(height=30),
            ft.Text("Pytania popkultura i muzyka boost:", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(height=20),
            ft.Row(menu_tiles_popkultura_muzyka, alignment=ft.MainAxisAlignment.CENTER, wrap=True),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=10,
        visible=True
    )

    # --- Funkcje Logiki Gry ---

    def update_money_display():
        txt_money.value = f"Twoja kasa: {game_state['money']} zł"
        if game_state["money"] <= 0:
            txt_money.value = "Kasa: 0 zł... KONIEC GRY"
            txt_money.color = "red_800"
        elif game_state["money"] < game_state["base_stake"]:
            txt_money.color = "orange_600"
        else:
            txt_money.color = "green_600"
        if page:
            page.update(txt_money)

    def update_spent_display():
        txt_money_spent.value = f"Wydano: {game_state['money_spent_on_hints']} zł"
        if page:
            page.update(txt_money_spent)

    def update_pot_display():
        txt_main_pot.value = f"AKTUALNA PULA: {game_state['main_pot']} zł"
        if page:
            page.update(txt_main_pot)

    def update_bonus_display():
        txt_bonus_pot.value = f"Bonus od banku: {game_state['current_bonus_pot']} zł"
        if page:
            page.update(txt_bonus_pot)

    def update_question_counter():
        idx = game_state["current_question_index"] + 1
        total = game_state["total_questions"]
        set_name = game_state["set_name"]
        txt_question_counter.value = f"Pytanie {idx} / {total} (Zestaw {set_name})"
        if page:
            page.update(txt_question_counter)

    def show_game_over(message: str):
        btn_hint_5050.disabled = True
        btn_buy_abcd.disabled = True
        btn_next.disabled = True
        txt_answer_field.disabled = True
        btn_submit_answer.disabled = True
        btn_bid_100.disabled = True
        btn_start_answering.disabled = True
        for btn in answers_container.controls:
            btn.disabled = True

        if page:
            page.update(btn_hint_5050, btn_buy_abcd, btn_next, txt_answer_field, btn_submit_answer, answers_container,
                        bidding_container)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Koniec Gry!"),
            content=ft.Text(message),
            actions=[
                ft.TextButton("Zagraj ten zestaw ponownie", on_click=lambda e: restart_current_set(e)),
                ft.TextButton("Wróć do menu", on_click=lambda e: go_to_main_menu(e))
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: go_to_main_menu(e)
        )
        page.dialog = dlg
        dlg.open = True
        if page:
            page.update()

    def check_game_over(minimum_needed: int, message: str):
        if game_state["money"] < minimum_needed:
            show_game_over(message)
            return True
        return False

    def check_answer(user_input: str):
        txt_answer_field.disabled = True
        btn_submit_answer.disabled = True
        btn_hint_5050.disabled = True
        btn_buy_abcd.disabled = True

        toggle_answer_buttons(disabled=True)

        current_q = game_state["active_question_set"][game_state["current_question_index"]]
        correct_text = current_q["correct"]

        pot_won = game_state["main_pot"]

        norm_user = normalize_answer(user_input)
        norm_correct = normalize_answer(correct_text)

        similarity = fuzz.ratio(norm_user, norm_correct)

        is_correct = similarity >= 80

        if is_correct:
            game_state["money"] += pot_won
            game_state["main_pot"] = 0
            txt_feedback.value = f"DOBRZE! (Podob. {similarity}%) Wygrywasz {pot_won} zł!\nPoprawna odp: {correct_text}"
            txt_feedback.color = "green"
        else:
            game_state["main_pot"] = pot_won
            txt_feedback.value = f"ŹLE... (Podob. {similarity}%) Pula {pot_won} zł przechodzi dalej.\nPoprawna odp: {correct_text}"
            txt_feedback.color = "red"

        if game_state["abcd_unlocked"]:
            clicked_button = None
            correct_button = None

            for btn in answers_container.controls:
                if btn.data == user_input:
                    clicked_button = btn
                if btn.data == correct_text:
                    correct_button = btn

            for btn in answers_container.controls:
                btn.visible = False

            if clicked_button:
                clicked_button.visible = True
                if is_correct:
                    clicked_button.style = ft.ButtonStyle(bgcolor="green_200", color="black")
                else:
                    clicked_button.style = ft.ButtonStyle(bgcolor="red_200", color="black")

            if not is_correct and correct_button:
                correct_button.visible = True
                correct_button.style = ft.ButtonStyle(bgcolor="green_200", color="black")

        update_money_display()
        update_pot_display()

        btn_next.visible = True
        btn_back_to_menu.visible = True

        if page:
            page.update(txt_feedback, btn_next, answers_container, txt_answer_field, btn_submit_answer, btn_hint_5050,
                        btn_buy_abcd, btn_back_to_menu)

    def handle_submit_answer(e):
        user_text = txt_answer_field.value
        check_answer(user_text)

    def handle_abcd_answer(e):
        selected_answer = e.control.data
        check_answer(selected_answer)

    def buy_hint_5050(e):
        if not game_state["abcd_unlocked"]:
            txt_feedback.value = "Podpowiedź 50/50 działa tylko z opcjami ABCD!"
            txt_feedback.color = "orange"
            if page: page.update(txt_feedback)
            return

        hint_cost = random.randint(500, 2500)

        if game_state["money"] < hint_cost:
            txt_feedback.value = f"{hint_cost}zł ? Ej mordeczko, tyle kasy to już nie masz :-)"
            txt_feedback.color = "orange"
            if page: page.update(txt_feedback)
            return

        game_state["money"] -= hint_cost
        game_state["money_spent_on_hints"] += hint_cost
        btn_hint_5050.disabled = True
        txt_feedback.value = f"Kupiono podpowiedź 50/50 za {hint_cost} zł."
        txt_feedback.color = "blue"
        update_money_display()
        update_spent_display()

        current_q = game_state["active_question_set"][game_state["current_question_index"]]
        correct_answer = current_q["correct"]

        wrong_answers = [ans for ans in current_q["answers"] if ans != correct_answer]
        random.shuffle(wrong_answers)
        to_remove = wrong_answers[:2]

        for btn in answers_container.controls:
            if btn.data in to_remove:
                btn.disabled = True

        if page:
            page.update(btn_hint_5050, txt_feedback, answers_container)

    def buy_abcd_options(e):
        cost = random.randint(1000, 3000)

        if game_state["money"] < cost:
            txt_feedback.value = f"{cost}zł ? Ej mordeczko, tyle kasy to już nie masz :-)"
            txt_feedback.color = "orange"
            if page: page.update(txt_feedback)
            return

        game_state["money"] -= cost
        game_state["money_spent_on_hints"] += cost
        game_state["abcd_unlocked"] = True
        update_money_display()
        update_spent_display()

        txt_answer_field.visible = False
        btn_submit_answer.visible = False

        answers_container.visible = True
        btn_buy_abcd.disabled = True
        btn_hint_5050.disabled = False

        txt_feedback.value = f"Kupiono opcje ABCD za {cost} zł."
        txt_feedback.color = "blue"

        q_data = game_state["active_question_set"][game_state["current_question_index"]]
        answers_container.controls.clear()
        shuffled_answers = q_data["answers"].copy()
        random.shuffle(shuffled_answers)

        for answer in shuffled_answers:
            answers_container.controls.append(
                ft.Button(
                    text=answer,
                    data=answer,
                    on_click=handle_abcd_answer,
                    width=400,
                    height=50,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
                )
            )

        if page:
            page.update(txt_answer_field, btn_submit_answer, answers_container, btn_buy_abcd, btn_hint_5050,
                        txt_feedback)

    def toggle_answer_buttons(disabled: bool):
        for btn in answers_container.controls:
            btn.disabled = disabled
            if not disabled:
                btn.visible = True
            if disabled:
                btn.style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
        if page:
            page.update(answers_container)

    def start_answering_and_load_question(e):
        game_state["current_question_index"] += 1

        if game_state["current_question_index"] >= game_state["total_questions"]:
            show_game_over(
                f"Gratulacje! Ukończyłeś zestaw {game_state['set_name']} z wynikiem {game_state['money']} zł!")
            return

        update_question_counter()

        q_data = game_state["active_question_set"][game_state["current_question_index"]]
        txt_question.value = q_data["question"]
        txt_question.visible = True

        bidding_container.visible = False
        txt_bonus_pot.visible = False

        answer_ui_container.visible = True
        txt_answer_field.visible = True
        txt_answer_field.disabled = False
        txt_answer_field.value = ""
        btn_submit_answer.visible = True
        btn_submit_answer.disabled = False

        btn_buy_abcd.disabled = False

        game_state["abcd_unlocked"] = False
        answers_container.visible = False
        answers_container.controls.clear()
        toggle_answer_buttons(disabled=False)
        for btn in answers_container.controls:
            btn.visible = True

        btn_hint_5050.disabled = True

        txt_feedback.value = "Odpowiedz na pytanie:"
        txt_feedback.color = "black"

        btn_submit_answer.on_click = handle_submit_answer
        btn_hint_5050.on_click = buy_hint_5050
        btn_buy_abcd.on_click = buy_abcd_options
        btn_next.on_click = start_bidding_phase

        if page:
            page.update(bidding_container, answer_ui_container, txt_answer_field,
                        btn_submit_answer, btn_buy_abcd, btn_hint_5050, txt_feedback,
                        answers_container, txt_question, txt_bonus_pot)

    def bid_100(e):
        bid_amount = 100
        current_bid = game_state["current_bid_amount"]
        max_bid = game_state["max_bid_per_round"]

        if check_game_over(bid_amount, "Próbowałeś zalicytować, ale nie masz już pieniędzy! Koniec gry."):
            return

        if current_bid >= max_bid:
            txt_feedback.value = f"Osiągnięto maksymalny limit licytacji ({max_bid} zł) w tej rundzie."
            txt_feedback.color = "orange"
            btn_bid_100.disabled = True
            if page: page.update(txt_feedback, btn_bid_100)
            return

        game_state["money"] -= bid_amount
        game_state["main_pot"] += bid_amount
        game_state["current_bid_amount"] += bid_amount

        target_bonus = (game_state["current_bid_amount"] // 1000) * 50
        current_bonus = game_state["current_bonus_pot"]

        if target_bonus > current_bonus:
            bonus_to_add = target_bonus - current_bonus
            game_state["main_pot"] += bonus_to_add
            game_state["current_bonus_pot"] = target_bonus
            update_bonus_display()
            txt_feedback.value = f"Bank dorzucił {bonus_to_add} zł bonusu!"
            txt_feedback.color = "blue"
        else:
            if txt_feedback.color == "blue":
                txt_feedback.value = ""
                txt_feedback.color = "black"

        update_money_display()
        update_pot_display()
        btn_bid_100.text = f"Licytuj +100 zł (Suma: {game_state['current_bid_amount']} zł)"

        if game_state["money"] < bid_amount:
            btn_bid_100.disabled = True
            txt_feedback.value = "Nie masz więcej pieniędzy na licytację."
            txt_feedback.color = "orange"
        elif game_state["current_bid_amount"] >= max_bid:
            btn_bid_100.disabled = True
            txt_feedback.value = f"Osiągnięto limit licytacji ({max_bid} zł)."
            txt_feedback.color = "orange"

        if page:
            page.update(btn_bid_100, txt_feedback)

    def start_bidding_phase(e=None):
        stake = game_state["base_stake"]

        if check_game_over(stake, f"Nie masz wystarczająco pieniędzy ({stake} zł), aby rozpocząć! Koniec gry."):
            return

        game_state["money"] -= stake
        game_state["main_pot"] += stake
        game_state["current_bid_amount"] = 0
        game_state["current_bonus_pot"] = 0
        update_money_display()
        update_pot_display()
        update_bonus_display()

        txt_feedback.value = f"Stawka {stake} zł dodana do puli. Licytuj!"
        txt_feedback.color = "black"

        txt_question.visible = False
        answer_ui_container.visible = False
        btn_next.visible = False
        btn_back_to_menu.visible = False
        btn_hint_5050.disabled = True
        btn_buy_abcd.disabled = True

        bidding_container.visible = True
        txt_bonus_pot.visible = True
        btn_bid_100.disabled = False
        btn_bid_100.text = "Licytuj +100 zł (Suma: 0 zł)"
        btn_start_answering.disabled = False

        btn_bid_100.on_click = bid_100
        btn_start_answering.on_click = start_answering_and_load_question

        if page:
            page.update(
                txt_question, answer_ui_container, txt_feedback, btn_hint_5050,
                btn_buy_abcd, btn_next, bidding_container, txt_bonus_pot, btn_back_to_menu
            )

    def reset_game_state():
        game_state["money"] = 10000
        game_state["current_question_index"] = -1
        game_state["main_pot"] = 0
        game_state["money_spent_on_hints"] = 0
        game_state["current_bid_amount"] = 0
        game_state["current_bonus_pot"] = 0

        update_money_display()
        update_pot_display()
        update_spent_display()
        update_bonus_display()

        if hasattr(page, 'dialog') and page.dialog:
            page.dialog.open = False

        txt_question.value = "Wciśnij 'Start', aby rozpocząć grę!"
        txt_question.visible = True
        txt_feedback.value = "Witaj w grze!"
        txt_feedback.color = "blue_700"

        bidding_container.visible = False
        answer_ui_container.visible = False
        btn_next.visible = False
        btn_back_to_menu.visible = False
        btn_hint_5050.disabled = True
        btn_buy_abcd.disabled = True

        if page:
            page.update(
                btn_next, txt_question, txt_feedback,
                bidding_container, answer_ui_container, btn_hint_5050,
                btn_buy_abcd, btn_back_to_menu
            )

    def go_to_main_menu(e):
        game_view.visible = False
        main_menu_view.visible = True
        main_menu_feedback.visible = False

        if hasattr(page, 'dialog') and page.dialog:
            page.dialog.open = False

        if page:
            page.update(game_view, main_menu_view, page.dialog, main_menu_feedback)

    def restart_current_set(e):
        if hasattr(page, 'dialog') and page.dialog:
            page.dialog.open = False
        reset_game_state()
        start_bidding_phase()
        if page:
            page.update()

    def start_game_session(e, set_filename: str):
        # Przekazujemy 'page' do parsera
        loaded_questions = parse_question_file(page, set_filename)

        if not loaded_questions:
            # Ta logika jest teraz kluczowa. Jeśli parse_question_file zwróci [],
            # to znaczy, że obie próby otwarcia pliku zawiodły.
            main_menu_feedback.value = f"BŁĄD KRYTYCZNY: Nie można wczytać pliku '{set_filename}'. Plik nie został znaleziony ani w 'assets/' ani w '/'."
            main_menu_feedback.visible = True
            if page: page.update(main_menu_feedback)
            return

        game_state["active_question_set"] = loaded_questions
        game_state["total_questions"] = len(loaded_questions)
        game_state["set_name"] = set_filename.replace(".txt", "")

        reset_game_state()

        main_menu_view.visible = False
        main_menu_feedback.visible = False
        game_view.visible = True

        start_bidding_phase()

        if page:
            page.update(main_menu_view, game_view, main_menu_feedback)

    # --- Układ Strony (Layout) ---
    btn_back_to_menu.on_click = go_to_main_menu
    btn_next.on_click = start_bidding_phase

    page.add(
        main_menu_view,
        game_view
    )

    if page:
        page.update()


# Uruchomienie aplikacji Flet
if __name__ == "__main__":
    # TA LINIA MUSI BYĆ, aby Flet wiedział, co spakować.
    # W połączeniu z flagą `--assets .` w main.yml, to powinno
    # poprawnie spakować pliki z katalogu głównego.
    ft.app(target=main, assets_dir=".")
