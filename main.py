import flet as ft
import random
import time
import re
import os
# Wymagana biblioteka do "fuzzy matching"
from thefuzz import fuzz

# --- STAŁA: Folder z zasobami ---
ASSETS_DIR = "assets"


# --------------------

def parse_question_file(filename: str) -> list:
    """
    Wczytuje plik .txt z folderu ASSETS_DIR i parsuje go do formatu listy pytań.
    Zwraca listę słowników [ { "question": ..., "correct": ..., "answers": [...] }, ... ]
    """
    parsed_questions = []

    # Tworzymy pełną ścieżkę do pliku w folderze 'assets'
    filepath = os.path.join(ASSETS_DIR, filename)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        # Usunięto print
        return []
    except Exception as e:
        # Usunięto print
        return []

    # Dzielimy plik na bloki na podstawie numeru pytania (np. "01.", "02.", "10.")
    question_blocks = re.split(r'\n(?=\d+\.)', content)

    for block in question_blocks:
        block = block.strip()
        if not block:
            continue

        # Stosujemy WZORZEC ELASTYCZNY do każdego pojedynczego bloku
        # Używamy (?:...) aby grupy nieprzechwytujące nie psuły kolejności .group()
        match = re.match(
            r"^\d+\.\s(.*?)\n"  # Grupa 1: Pytanie
            # Elastyczna linia dla "prawidłowa odpowiedź = "
            r"prawid(?:l|ł)owa\s+odpowied(?:z|ź)\s*=\s*(.*?)\n"  # Grupa 2: Prawidłowa odpowiedź
            # Elastyczna linia dla "odpowiedz ABCD = "
            r"odpowied(?:z|ź)\s+abcd\s*=\s*A\s*=\s*(.*?), B\s*=\s*(.*?), C\s*=\s*(.*?), D\s*=\s*(.*?)$",
            block, re.DOTALL | re.IGNORECASE  # Flagi: DOTALL (. działa na linie) i IGNORECASE (ignoruj wielk. liter)
        )

        if match:
            try:
                # Grupa 1: Pytanie
                question = match.group(1).strip()
                # Grupa 2: Prawidłowa odpowiedź (Teraz poprawnie)
                correct = match.group(2).strip()
                # Grupy 3-6: Odpowiedzi ABCD (Teraz poprawnie)
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
                # Usunięto print
                pass
        else:
            # Usunięto print
            pass

    return parsed_questions


def normalize_answer(text: str) -> str:
    """
    Normalizuje odpowiedź:
    - usuwa wielkość liter
    - usuwa spacje na początku i końcu
    - zamienia polskie diakrytyki (ó->o, ł->l, ż/ź->z, itp.)
    - zamienia 'u' na 'o' (zgodnie z prośbą ó-u-o)
    - usuwa wszystkie wewnętrzne spacje (zgodnie z "mounteverest")
    """
    text = str(text).lower().strip()

    # Słownik zamian diakrytyków
    diacritics = {
        'ó': 'o', 'ł': 'l', 'ż': 'z', 'ź': 'z', 'ć': 'c',
        'ń': 'n', 'ś': 's', 'ą': 'a', 'ę': 'e', 'ü': 'u'
    }

    for char, replacement in diacritics.items():
        text = text.replace(char, replacement)

    # Zamiana 'u' na 'o' (jak w 'ó-u-o')
    text = text.replace('u', 'o')

    # Usunięcie wszystkich spacji
    text = "".join(text.split())

    return text


def main(page: ft.Page):
    page.title = "Awantura o Kasę - Singleplayer"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.window_width = 600
    page.window_height = 800
    page.theme_mode = ft.ThemeMode.LIGHT

    # --- Zmienne stanu gry ---
    game_state = {
        "money": 10000,
        "current_question_index": -1,
        "base_stake": 500,  # Kwota stawki za pytanie
        "abcd_unlocked": False,
        "main_pot": 0,  # Główna pula wygranej
        "money_spent_on_hints": 0,  # Licznik wydatków
        "current_bid_amount": 0,  # Ile zalicytowano w tej rundzie
        "max_bid_per_round": 5000,  # Limit licytacji na rundę
        "current_bonus_pot": 0,
        "active_question_set": [],  # Lista pytań załadowana z pliku
        "total_questions": 0,  # Całkowita liczba pytań w zestawie
        "set_name": ""  # Nazwa zestawu (np. "01")
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
            answers_container,  # Kontener na przyciski ABCD
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False  # Ukryty na starcie
    )

    # --- Kontrolki UI Licytacji (grupowane) ---
    btn_bid_100 = ft.Button(
        text="Licytuj +100 zł (Suma: 0 zł)",
        icon="add",
        on_click=None,
        width=400,
    )

    btn_start_answering = ft.Button(
        text="Pokaż pytanie",  # Zmieniony tekst
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
        visible=False  # Ukryty na starcie
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
        on_click=None,  # Przypiszemy później
        width=400,
        visible=False,  # Pokażemy po zakończeniu pytania
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

            ft.Container(
                content=txt_question,
                alignment=ft.alignment.center,
                padding=ft.padding.only(left=20, right=20, top=10, bottom=10),
                height=100
            ),

            bidding_container,
            answer_ui_container,

            ft.Divider(height=20, color="transparent"),

            # ZMIANA KOLEJNOŚCI TUTAJ
            ft.Column(
                [
                    btn_hint_5050,
                    btn_buy_abcd,
                    btn_next,
                    txt_feedback,  # Przeniesiony tutaj
                    btn_back_to_menu,
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            )
        ],
        visible=False  # Na starcie ukryty
    )

    # --- WIDOK 2: EKRAN GŁÓWNY (MENU) ---
    menu_tiles_standard = []
    for i in range(1, 31):
        filename = f"{i:02d}.txt"
        filepath = os.path.join(ASSETS_DIR, filename)
        file_exists = os.path.exists(filepath)

        menu_tiles_standard.append(
            ft.Button(
                # ZMIANA: Używamy 'content' zamiast 'text' aby kontrolować czcionkę
                content=ft.Text(value=f"{i:02d}", size=12),
                tooltip=f"Zestaw {i:02d}",
                width=35,  # ZMIANA: Mniejszy przycisk
                height=35, # ZMIANA: Mniejszy przycisk
                on_click=lambda e, f=filename: start_game_session(e, f),
                disabled=not file_exists,
                style=ft.ButtonStyle(
                    bgcolor="blue_grey_50" if file_exists else "grey_300"
                )
            )
        )

    menu_tiles_popkultura = []
    for i in range(31, 41):
        filename = f"{i:02d}.txt"
        filepath = os.path.join(ASSETS_DIR, filename)
        file_exists = os.path.exists(filepath)

        menu_tiles_popkultura.append(
            ft.Button(
                content=ft.Text(value=f"{i:02d}", size=12),
                tooltip=f"Zestaw {i:02d}",
                width=35,  # ZMIANA
                height=35, # ZMIANA
                on_click=lambda e, f=filename: start_game_session(e, f),
                disabled=not file_exists,
                style=ft.ButtonStyle(
                    bgcolor="deep_purple_50" if file_exists else "grey_300"
                )
            )
        )

    menu_tiles_popkultura_muzyka = []
    for i in range(41, 51):
        filename = f"{i:02d}.txt"
        filepath = os.path.join(ASSETS_DIR, filename)
        file_exists = os.path.exists(filepath)

        menu_tiles_popkultura_muzyka.append(
            ft.Button(
                content=ft.Text(value=f"{i:02d}", size=12),
                tooltip=f"Zestaw {i:02d}",
                width=35,  # ZMIANA
                height=35, # ZMIANA
                on_click=lambda e, f=filename: start_game_session(e, f),
                disabled=not file_exists,
                style=ft.ButtonStyle(
                    bgcolor="amber_50" if file_exists else "grey_300"
                )
            )
        )

    main_menu_view = ft.Column(
        [
            ft.Text("Wybierz zestaw pytań:", size=24, weight=ft.FontWeight.BOLD),
            ft.Text(f"Dostępne są tylko podświetlone zestawy (pliki .txt w folderze '{ASSETS_DIR}')."),
            ft.Divider(height=20),
            ft.Row(menu_tiles_standard[0:10], alignment=ft.MainAxisAlignment.CENTER, wrap=True),
            ft.Row(menu_tiles_standard[10:20], alignment=ft.MainAxisAlignment.CENTER, wrap=True),
            ft.Row(menu_tiles_standard[20:30], alignment=ft.MainAxisAlignment.CENTER, wrap=True),

            ft.Divider(height=30),
            ft.Text("Pytania popkultura Boost:", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(height=20),
            ft.Row(menu_tiles_popkultura, alignment=ft.MainAxisAlignment.CENTER, wrap=True),

            ft.Divider(height=30),
            ft.Text("Pytania popkultura i muzyka boost:", size=24, weight=f"t.FontWeight.BOLD"),
            ft.Divider(height=20),
            ft.Row(menu_tiles_popkultura_muzyka, alignment=ft.MainAxisAlignment.CENTER, wrap=True),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=10,
        visible=True  # Widoczny na starcie
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
        """Aktualizuje licznik pytań (np. 01/50)."""
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
            on_dismiss=lambda e: go_to_main_menu(e)  # Domyślnie wróć do menu
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

        # Nowa logika ukrywania przycisków
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
            game_state["main_pot"] = 0  # Resetuj pulę
            txt_feedback.value = f"DOBRZE! (Podob. {similarity}%) Wygrywasz {pot_won} zł!\nPoprawna odp: {correct_text}"
            txt_feedback.color = "green"
        else:
            game_state["main_pot"] = pot_won  # Pula zostaje
            txt_feedback.value = f"ŹLE... (Podob. {similarity}%) Pula {pot_won} zł przechodzi dalej.\nPoprawna odp: {correct_text}"
            txt_feedback.color = "red"

        # --- NOWA LOGIKA UKRYWANIA I STYLOWANIA ABCD ---
        if game_state["abcd_unlocked"]:
            clicked_button = None
            correct_button = None

            # Znajdź przyciski
            for btn in answers_container.controls:
                if btn.data == user_input:
                    clicked_button = btn
                if btn.data == correct_text:
                    correct_button = btn

            # Ukryj wszystkie przyciski
            for btn in answers_container.controls:
                btn.visible = False

            # Pokaż i styluj ten, który kliknąłeś
            if clicked_button:
                clicked_button.visible = True
                if is_correct:
                    clicked_button.style = ft.ButtonStyle(bgcolor="green_200", color="black")
                else:
                    clicked_button.style = ft.ButtonStyle(bgcolor="red_200", color="black")

            # Pokaż i styluj poprawny (jeśli byłeś w błędzie i nie jest to ten sam przycisk)
            if not is_correct and correct_button:
                correct_button.visible = True
                correct_button.style = ft.ButtonStyle(bgcolor="green_200", color="black")
        # --- KONIEC NOWEJ LOGIKI ---

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
        # Ta funkcja teraz tylko przekazuje odpowiedź. Resztę robi check_answer.
        selected_answer = e.control.data
        check_answer(selected_answer)

    def buy_hint_5050(e):
        if not game_state["abcd_unlocked"]:
            txt_feedback.value = "Podpowiedź 50/50 działa tylko z opcjami ABCD!"
            txt_feedback.color = "orange"
            if page: page.update(txt_feedback)
            return

        hint_cost = random.randint(500, 2500)

        # --- POPRAWKA TUTAJ ---
        if game_state["money"] < hint_cost:
            txt_feedback.value = f"{hint_cost}zł ? Ej mordeczko, tyle kasy to już nie masz :-)"
            txt_feedback.color = "orange"
            if page: page.update(txt_feedback)
            return
        # --- KONIEC POPRAWKI ---

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

        # --- POPRAWKA TUTAJ ---
        if game_state["money"] < cost:
            txt_feedback.value = f"{cost}zł ? Ej mordeczko, tyle kasy to już nie masz :-)"
            txt_feedback.color = "orange"
            if page: page.update(txt_feedback)
            return
        # --- KONIEC POPRAWKI ---

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
            if disabled:
                # Resetuj styl, ale nie widoczność
                btn.style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
        if page:
            page.update(answers_container)

    # --- Funkcje Licytacji ---
    def start_answering_and_load_question(e):
        """Kończy licytację, WCZYTUJE i POKAZUJE pytanie, pokazuje UI odpowiedzi."""

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
        """Dodaje 100 zł do puli z kasy gracza."""
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

    # --- Główne Funkcje Nawigacji ---

    def start_bidding_phase(e=None):
        """Rozpoczyna FAZĘ LICYTACJI. Ukrywa pytanie."""

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

        txt_question.visible = False  # KLUCZOWA ZMIANA
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
        """Resetuje stan kasy i puli, ale NIE wczytuje pytań."""
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
        """Pokazuje menu główne, ukrywa widok gry."""
        game_view.visible = False
        main_menu_view.visible = True

        if hasattr(page, 'dialog') and page.dialog:
            page.dialog.open = False

        if page:
            page.update(game_view, main_menu_view, page.dialog)

    def restart_current_set(e):
        """Resetuje stan gry i zaczyna ten sam zestaw od nowa."""
        if hasattr(page, 'dialog') and page.dialog:
            page.dialog.open = False
        reset_game_state()
        start_bidding_phase()
        if page:
            page.update()

    def start_game_session(e, set_filename: str):
        """
        Główna funkcja wczytująca zestaw pytań i przełączająca widok.
        """
        loaded_questions = parse_question_file(set_filename)

        if not loaded_questions:
            # Usunięto print
            return

        game_state["active_question_set"] = loaded_questions
        game_state["total_questions"] = len(loaded_questions)
        game_state["set_name"] = set_filename.replace(".txt", "")

        reset_game_state()

        main_menu_view.visible = False
        game_view.visible = True

        start_bidding_phase()

        if page:
            page.update(main_menu_view, game_view)

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
    ft.app(target=main)
