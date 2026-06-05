import json
import os
import random
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


DATA_DIR = Path("data")
PLAYERS_FILE = DATA_DIR / "players.json"
ROOMS_FILE = DATA_DIR / "rooms.json"
EVENTS_FILE = DATA_DIR / "events.json"

TOMIKI = "tomiki"
HOPIKI = "hopiki"
TOMIKI_NAME = "Томики 🟦"
HOPIKI_NAME = "Хопики 🟨"
DEFAULT_TOMIKI_BALANCE = 1000
DEFAULT_HOPIKI_BALANCE = 1000

ROOMS: dict[str, dict[str, Any]] = {}
EVENTS: dict[str, dict[str, Any]] = {}
PLAYERS: dict[str, dict[str, Any]] = {}

ROOM_SETTINGS: dict[str, Any] = {
    "return_if_no_winner": True,
}

EVENT_SETTINGS: dict[str, Any] = {
    "allow_change_bet": False,
    "return_bets_on_cancel": True,
    "return_bets_if_no_winner": True,
    "admin_can_refund": True,
}

GAME_ALIASES = {
    "кубик": "dice",
    "dice": "dice",
    "слоты": "slots",
    "slots": "slots",
    "рулетка": "roulette",
    "roulette": "roulette",
}

GAME_TITLES = {
    "dice": "Кубик",
    "slots": "Слоты",
    "roulette": "Рулетка",
}

CURRENCY_ALIASES = {
    "tomiki": TOMIKI,
    "томики": TOMIKI,
    "t": TOMIKI,
    "hopiki": HOPIKI,
    "хопики": HOPIKI,
    "h": HOPIKI,
}

ROULETTE_ALIASES = {
    "красное": "red",
    "red": "red",
    "черное": "black",
    "чёрное": "black",
    "black": "black",
    "зеро": "zero",
    "zero": "zero",
}

ROULETTE_TITLES = {
    "red": "красное",
    "black": "чёрное",
    "zero": "зеро",
}

SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "⭐", "💎", "7"]

DICE_BET_ALIASES = {
    "больше": "high",
    "high": "high",
    "меньше": "low",
    "low": "low",
    "чёт": "even",
    "чет": "even",
    "even": "even",
    "нечёт": "odd",
    "нечет": "odd",
    "odd": "odd",
}

DICE_BET_TITLES = {
    "high": "больше 3",
    "low": "меньше 4",
    "even": "чёт",
    "odd": "нечёт",
}

SHOP_ITEMS: dict[str, dict[str, Any]] = {
    "1": {
        "name": "Блестящий камушек",
        "description": "Просто красивый сувенир для профиля.",
        "currency": TOMIKI,
        "price": 100,
    },
    "2": {
        "name": "Мини-корона",
        "description": "Безделушка для тех, кто любит побеждать красиво.",
        "currency": TOMIKI,
        "price": 350,
    },
    "3": {
        "name": "Жёлтый талисман",
        "description": "Маленький талисман удачи.",
        "currency": HOPIKI,
        "price": 150,
    },
    "4": {
        "name": "Золотой билетик",
        "description": "Коллекционный билет без реальной ценности.",
        "currency": HOPIKI,
        "price": 500,
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def setup_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not PLAYERS_FILE.exists():
        save_json(PLAYERS_FILE, {})
    if not ROOMS_FILE.exists():
        save_json(
            ROOMS_FILE,
            {
                "rooms": {},
                "room_settings": ROOM_SETTINGS,
            },
        )
    if not EVENTS_FILE.exists():
        save_json(
            EVENTS_FILE,
            {
                "events": {},
                "event_settings": EVENT_SETTINGS,
            },
        )


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_data() -> None:
    global PLAYERS, ROOMS, EVENTS, ROOM_SETTINGS, EVENT_SETTINGS

    setup_files()
    PLAYERS = load_json(PLAYERS_FILE, {})

    rooms_data = load_json(ROOMS_FILE, {})
    ROOMS = rooms_data.get("rooms", {})
    ROOM_SETTINGS = rooms_data.get("room_settings", ROOM_SETTINGS)

    events_data = load_json(EVENTS_FILE, {})
    EVENTS = events_data.get("events", {})
    EVENT_SETTINGS = events_data.get("event_settings", EVENT_SETTINGS)


def save_players() -> None:
    save_json(PLAYERS_FILE, PLAYERS)


def save_rooms() -> None:
    save_json(
        ROOMS_FILE,
        {
            "rooms": ROOMS,
            "room_settings": ROOM_SETTINGS,
        },
    )


def save_events() -> None:
    save_json(
        EVENTS_FILE,
        {
            "events": EVENTS,
            "event_settings": EVENT_SETTINGS,
        },
    )


def user_id(update: Update) -> str:
    if update.effective_user is None:
        raise ValueError("Нет пользователя в Telegram update.")
    return str(update.effective_user.id)


def chat_id(update: Update) -> int:
    if update.effective_chat is None:
        raise ValueError("Нет чата в Telegram update.")
    return update.effective_chat.id


def is_group_chat(update: Update) -> bool:
    return update.effective_chat is not None and update.effective_chat.type in {"group", "supergroup"}


def display_name(update: Update) -> str:
    user = update.effective_user
    if user is None:
        return "Игрок"
    return user.full_name or user.username or str(user.id)


def get_player(player_id: str, name: str = "Игрок") -> dict[str, Any]:
    if player_id not in PLAYERS:
        PLAYERS[player_id] = {
            "id": player_id,
            "name": name,
            TOMIKI: DEFAULT_TOMIKI_BALANCE,
            HOPIKI: DEFAULT_HOPIKI_BALANCE,
            "items": [],
            "bet_history": [],
            "created_at": now_iso(),
        }
        save_players()
    else:
        PLAYERS[player_id]["name"] = name
        PLAYERS[player_id].setdefault(TOMIKI, DEFAULT_TOMIKI_BALANCE)
        PLAYERS[player_id].setdefault(HOPIKI, DEFAULT_HOPIKI_BALANCE)
        PLAYERS[player_id].setdefault("items", [])
        PLAYERS[player_id].setdefault("bet_history", [])
    return PLAYERS[player_id]


def currency_title(currency: str) -> str:
    return TOMIKI_NAME if currency == TOMIKI else HOPIKI_NAME


def parse_currency(raw: str) -> str | None:
    return CURRENCY_ALIASES.get(raw.strip().lower())


def parse_game(raw: str) -> str | None:
    return GAME_ALIASES.get(raw.strip().lower())


def parse_roulette_choice(raw: str) -> str | None:
    return ROULETTE_ALIASES.get(raw.strip().lower())


def parse_dice_bet(raw: str) -> str | int | None:
    value = raw.strip().lower()
    if value.isdigit():
        number = int(value)
        if 1 <= number <= 6:
            return number
        return None
    return DICE_BET_ALIASES.get(value)


def is_admin(player_id: str) -> bool:
    admin_ids = os.getenv("ADMIN_IDS", "")
    allowed_ids = {admin_id.strip() for admin_id in admin_ids.split(",") if admin_id.strip()}
    return player_id in allowed_ids


def require_admin(update: Update) -> bool:
    return is_admin(user_id(update))


def can_pay(player: dict[str, Any], currency: str, amount: int) -> bool:
    return amount > 0 and int(player.get(currency, 0)) >= amount


def add_history(
    player_id: str,
    history_type: str,
    title: str,
    result: str,
    currency: str,
    bet_amount: int,
    payout_amount: int,
) -> None:
    player = PLAYERS[player_id]
    player.setdefault("bet_history", []).append(
        {
            "type": history_type,
            "title": title,
            "result": result,
            "currency": currency,
            "bet_amount": bet_amount,
            "payout_amount": payout_amount,
            "date": now_iso(),
        }
    )


def main_menu(player_is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🎮 Играть одному", callback_data="menu_solo")],
        [InlineKeyboardButton("🤝 Игры с друзьями", callback_data="menu_rooms")],
        [InlineKeyboardButton("📢 События", callback_data="menu_events")],
        [InlineKeyboardButton("📜 История ставок", callback_data="menu_history")],
    ]
    if player_is_admin:
        buttons.append([InlineKeyboardButton("🛠 Админ-панель", callback_data="menu_admin")])
    return InlineKeyboardMarkup(buttons)


def solo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Кубик", callback_data="solo_dice_help")],
            [InlineKeyboardButton("Слоты", callback_data="solo_slots_help")],
            [InlineKeyboardButton("Рулетка", callback_data="solo_roulette_help")],
            [InlineKeyboardButton("Назад", callback_data="menu_main")],
        ]
    )


def rooms_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Создать комнату", callback_data="room_create_help")],
            [InlineKeyboardButton("Войти по коду", callback_data="room_join_help")],
            [InlineKeyboardButton("Активные комнаты", callback_data="room_list")],
            [InlineKeyboardButton("Назад", callback_data="menu_main")],
        ]
    )


def events_keyboard(player_is_admin: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Открытые события", callback_data="event_list")],
        [InlineKeyboardButton("Как поставить ставку", callback_data="event_bet_help")],
        [InlineKeyboardButton("Назад", callback_data="menu_main")],
    ]
    if player_is_admin:
        buttons.insert(0, [InlineKeyboardButton("Создать событие", callback_data="event_create_help")])
    return InlineKeyboardMarkup(buttons)


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Создать событие", callback_data="event_create_help")],
            [InlineKeyboardButton("Управление событиями", callback_data="admin_event_help")],
            [InlineKeyboardButton("Выдать валюту/предмет", callback_data="admin_give_help")],
            [InlineKeyboardButton("Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("Назад", callback_data="menu_main")],
        ]
    )


def generate_room_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choice(alphabet) for _ in range(5))
        if code not in ROOMS:
            return code


def active_rooms_text(target_chat_id: int | None = None) -> str:
    active_rooms = [
        room
        for room in ROOMS.values()
        if room["status"] == "waiting"
        and (target_chat_id is None or room.get("chat_id") == target_chat_id)
    ]
    if not active_rooms:
        return "Сейчас нет комнат в ожидании игроков."

    lines = ["🤝 Активные комнаты:"]
    for room in active_rooms:
        lines.append(
            f"\nКод: <b>{room['code']}</b>\n"
            f"Игра: {GAME_TITLES[room['game']]}\n"
            f"Игроки: {len(room['players'])}/{room['max_players']}\n"
            f"Ставка: {room['bet_amount']} {currency_title(room['currency'])}"
        )
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = get_player(user_id(update), display_name(update))
    if is_group_chat(update):
        text = (
            "Бот подключён к группе.\n\n"
            "Здесь можно играть на виртуальные Томики 🟦 и Хопики 🟨 прямо командами группы.\n"
            "Комнаты с друзьями:\n"
            "/create_room кубик 3 tomiki 100\n"
            "/join_room AB123\n"
            "/rooms\n\n"
            "Одиночные ставки:\n"
            "/dice 6 tomiki 100\n"
            "/slots hopiki 50\n"
            "/roulette красное tomiki 100\n\n"
            "Магазин:\n"
            "/shop\n"
            "/buy_item 1\n"
            "/inventory\n\n"
            "События:\n"
            "/events\n"
            "/bet_event 1 2 tomiki 100\n\n"
            "Важно: это только виртуальная валюта, без реальных денег."
        )
        await update.effective_message.reply_text(
            text,
            reply_markup=main_menu(is_admin(player["id"])),
        )
        return

    text = (
        f"Привет, {player['name']}!\n\n"
        "Это бот с виртуальными Томиками 🟦 и Хопиками 🟨.\n"
        "Здесь нет реальных денег, пополнений, вывода средств, криптовалюты или настоящего казино."
    )
    await update.effective_message.reply_text(
        text,
        reply_markup=main_menu(is_admin(player["id"])),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    get_player(user_id(update), display_name(update))
    text = (
        "Команды бота:\n\n"
        "Баланс и история:\n"
        "/balance\n"
        "/bet_history\n\n"
        "Магазин безделушек:\n"
        "/shop\n"
        "/buy_item 1\n"
        "/inventory\n\n"
        "Играть одному:\n"
        "/dice 6 tomiki 100\n"
        "/dice больше hopiki 50\n"
        "/slots tomiki 100\n"
        "/roulette красное tomiki 100\n\n"
        "Игры с друзьями в группе:\n"
        "/create_room кубик 3 tomiki 100\n"
        "/create_room слоты 2 hopiki 50\n"
        "/create_room рулетка 4 tomiki 100 красное\n"
        "/join_room AB123\n"
        "/rooms\n"
        "/leave_room\n\n"
        "События:\n"
        "/events\n"
        "/event 1\n"
        "/bet_event 1 2 tomiki 100\n\n"
        "Админ-команды работают только для ID из ADMIN_IDS."
    )
    if is_group_chat(update):
        text += "\n\nЕсли бот не реагирует в группе, у @BotFather отключи Privacy Mode для этого бота."
    await update.effective_message.reply_text(text)


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = get_player(user_id(update), display_name(update))
    await update.effective_message.reply_text(
        f"Баланс:\n"
        f"Томики 🟦: {player.get(TOMIKI, 0)}\n"
        f"Хопики 🟨: {player.get(HOPIKI, 0)}"
    )


async def solo_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.effective_message.reply_text(
            "Формат:\n"
            "/solo_game игра валюта ставка [выбор]\n\n"
            "Примеры:\n"
            "/solo_game кубик tomiki 100 6\n"
            "/solo_game слоты hopiki 50\n"
            "/solo_game рулетка tomiki 100 красное"
        )
        return

    game = parse_game(context.args[0])
    currency = parse_currency(context.args[1])
    try:
        amount = int(context.args[2])
    except ValueError:
        await update.effective_message.reply_text("Ставка должна быть числом.")
        return

    roulette_choice = None
    dice_bet = None
    if game == "dice":
        if len(context.args) < 4:
            await update.effective_message.reply_text(
                "Для кубика укажи ставку: число 1-6, больше, меньше, чёт или нечёт.\n"
                "Пример: /solo_game кубик tomiki 100 6"
            )
            return
        dice_bet = parse_dice_bet(context.args[3])
    if game == "roulette":
        if len(context.args) < 4:
            await update.effective_message.reply_text(
                "Для рулетки укажи цвет: красное, чёрное или зеро.\n"
                "Пример: /solo_game рулетка tomiki 100 красное"
            )
            return
        roulette_choice = parse_roulette_choice(context.args[3])

    await play_solo_game(update, game, currency, amount, roulette_choice, dice_bet)


async def solo_dice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.effective_message.reply_text(
            "Формат: /dice выбор tomiki 100\n"
            "Выбор: число 1-6, больше, меньше, чёт или нечёт."
        )
        return
    dice_bet = parse_dice_bet(context.args[0])
    currency = parse_currency(context.args[1])
    try:
        amount = int(context.args[2])
    except ValueError:
        await update.effective_message.reply_text("Ставка должна быть числом.")
        return
    await play_solo_game(update, "dice", currency, amount, dice_bet=dice_bet)


async def solo_slots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.effective_message.reply_text("Формат: /slots tomiki 100")
        return
    currency = parse_currency(context.args[0])
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("Ставка должна быть числом.")
        return
    await play_solo_game(update, "slots", currency, amount)


async def solo_roulette(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.effective_message.reply_text("Формат: /roulette красное tomiki 100")
        return
    roulette_choice = parse_roulette_choice(context.args[0])
    currency = parse_currency(context.args[1])
    try:
        amount = int(context.args[2])
    except ValueError:
        await update.effective_message.reply_text("Ставка должна быть числом.")
        return
    await play_solo_game(update, "roulette", currency, amount, roulette_choice)


async def play_solo_game(
    update: Update,
    game: str | None,
    currency: str | None,
    amount: int,
    roulette_choice: str | None = None,
    dice_bet: str | int | None = None,
) -> None:
    player_id = user_id(update)
    player = get_player(player_id, display_name(update))

    if game not in {"dice", "slots", "roulette"}:
        await update.effective_message.reply_text("Игра должна быть: кубик, слоты или рулетка.")
        return
    if currency is None:
        await update.effective_message.reply_text("Валюта должна быть: tomiki или hopiki.")
        return
    if amount <= 0:
        await update.effective_message.reply_text("Ставка должна быть больше нуля.")
        return
    if not can_pay(player, currency, amount):
        await update.effective_message.reply_text("Не хватает валюты для ставки.")
        return
    if game == "dice" and dice_bet is None:
        await update.effective_message.reply_text(
            "Для кубика выбери ставку: число 1-6, больше, меньше, чёт или нечёт."
        )
        return
    if game == "roulette" and roulette_choice is None:
        await update.effective_message.reply_text("Цвет должен быть: красное, чёрное или зеро.")
        return

    player[currency] -= amount
    title, result, payout, lines = calculate_solo_game(game, amount, roulette_choice, dice_bet)
    if payout > 0:
        player[currency] += payout

    add_history(
        player_id,
        "solo_game",
        title,
        result,
        currency,
        amount,
        payout,
    )
    save_players()

    lines.append("")
    lines.append(f"Ставка: {amount} {currency_title(currency)}")
    lines.append(f"Получено: {payout} {currency_title(currency)}")
    lines.append(f"Баланс: {player[currency]} {currency_title(currency)}")
    await update.effective_message.reply_text("\n".join(lines))


def calculate_solo_game(
    game: str,
    amount: int,
    roulette_choice: str | None,
    dice_bet: str | int | None,
) -> tuple[str, str, int, list[str]]:
    if game == "dice":
        roll = random.randint(1, 6)
        assert dice_bet is not None
        won = is_dice_bet_winner(roll, dice_bet)
        multiplier = dice_bet_multiplier(dice_bet) if won else 0
        payout = amount * multiplier
        result = "выигрыш" if won else "поражение"
        lines = [
            "🎲 Ставка на кубик",
            f"Твой выбор: {dice_bet_title(dice_bet)}",
            f"Выпало: {roll}",
            f"Множитель: x{multiplier}",
        ]
        return "Кубик одному", result, payout, lines

    if game == "slots":
        symbols = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        score = slot_score(symbols)
        multiplier = solo_slots_multiplier(symbols, score)
        payout = amount * multiplier
        result = "выигрыш" if payout > 0 else "поражение"
        lines = [
            "🎰 Игра одному: Слоты",
            f"Выпало: {' '.join(symbols)}",
            f"Очки: {score}",
            f"Множитель: x{multiplier}",
        ]
        return "Слоты одному", result, payout, lines

    roulette_result = random.choice(["red", "black", "zero"])
    assert roulette_choice is not None
    if roulette_choice == roulette_result:
        multiplier = 14 if roulette_choice == "zero" else 2
        payout = amount * multiplier
        result = "выигрыш"
    else:
        multiplier = 0
        payout = 0
        result = "поражение"

    lines = [
        "🎡 Игра одному: Рулетка",
        f"Твой выбор: {ROULETTE_TITLES[roulette_choice]}",
        f"Выпало: {ROULETTE_TITLES[roulette_result]}",
        f"Множитель: x{multiplier}",
    ]
    return "Рулетка одному", result, payout, lines


def solo_slots_multiplier(symbols: list[str], score: int) -> int:
    if symbols == ["7", "7", "7"]:
        return 5
    if symbols == ["💎", "💎", "💎"]:
        return 4
    if score == 100:
        return 3
    if score == 40:
        return 2
    return 0


def is_dice_bet_winner(roll: int, dice_bet: str | int) -> bool:
    if isinstance(dice_bet, int):
        return roll == dice_bet
    if dice_bet == "high":
        return roll >= 4
    if dice_bet == "low":
        return roll <= 3
    if dice_bet == "even":
        return roll % 2 == 0
    if dice_bet == "odd":
        return roll % 2 == 1
    return False


def dice_bet_multiplier(dice_bet: str | int) -> int:
    if isinstance(dice_bet, int):
        return 6
    return 2


def dice_bet_title(dice_bet: str | int) -> str:
    if isinstance(dice_bet, int):
        return str(dice_bet)
    return DICE_BET_TITLES[dice_bet]


async def create_room(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player_id = user_id(update)
    player = get_player(player_id, display_name(update))
    args = context.args

    if len(args) < 4:
        await update.effective_message.reply_text(
            "Формат:\n"
            "/create_room игра игроки валюта ставка [цвет]\n\n"
            "Примеры:\n"
            "/create_room кубик 3 tomiki 100\n"
            "/create_room слоты 2 hopiki 50\n"
            "/create_room рулетка 4 tomiki 100 красное"
        )
        return

    game = parse_game(args[0])
    if game is None:
        await update.effective_message.reply_text("Игра должна быть: кубик, слоты или рулетка.")
        return

    try:
        max_players = int(args[1])
        bet_amount = int(args[3])
    except ValueError:
        await update.effective_message.reply_text("Количество игроков и ставка должны быть числами.")
        return

    currency = parse_currency(args[2])
    if currency is None:
        await update.effective_message.reply_text("Валюта должна быть: tomiki или hopiki.")
        return

    if max_players not in [2, 3, 4]:
        await update.effective_message.reply_text("Комната может быть только на 2, 3 или 4 игрока.")
        return

    if bet_amount <= 0:
        await update.effective_message.reply_text("Ставка должна быть больше нуля.")
        return

    roulette_choice = None
    if game == "roulette":
        if len(args) < 5:
            await update.effective_message.reply_text(
                "Для рулетки укажи цвет: красное, чёрное или зеро.\n"
                "Пример: /create_room рулетка 3 tomiki 100 красное"
            )
            return
        roulette_choice = parse_roulette_choice(args[4])
        if roulette_choice is None:
            await update.effective_message.reply_text("Цвет должен быть: красное, чёрное или зеро.")
            return

    if not can_pay(player, currency, bet_amount):
        await update.effective_message.reply_text("Не хватает валюты для ставки.")
        return

    player[currency] -= bet_amount
    code = generate_room_code()
    ROOMS[code] = {
        "code": code,
        "game": game,
        "max_players": max_players,
        "currency": currency,
        "bet_amount": bet_amount,
        "status": "waiting",
        "players": [player_id],
        "creator": player_id,
        "chat_id": chat_id(update),
        "chat_type": update.effective_chat.type if update.effective_chat else "private",
        "choices": {},
        "results": {},
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
    }
    if roulette_choice:
        ROOMS[code]["choices"][player_id] = roulette_choice

    save_players()
    save_rooms()

    await update.effective_message.reply_text(
        f"Комната создана!\n\n"
        f"Код комнаты: <b>{code}</b>\n"
        f"Игра: {GAME_TITLES[game]}\n"
        f"Игроки: 1/{max_players}\n"
        f"Ставка: {bet_amount} {currency_title(currency)}",
        parse_mode=ParseMode.HTML,
    )


async def join_room(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player_id = user_id(update)
    player = get_player(player_id, display_name(update))
    args = context.args

    if not args:
        await update.effective_message.reply_text(
            "Формат:\n"
            "/join_room код [цвет]\n\n"
            "Для рулетки цвет обязателен: красное, чёрное или зеро."
        )
        return

    code = args[0].upper()
    room = ROOMS.get(code)
    if room is None:
        await update.effective_message.reply_text("Комната не найдена.")
        return

    if room["status"] != "waiting":
        await update.effective_message.reply_text("Игра уже началась или завершена.")
        return

    if player_id in room["players"]:
        await update.effective_message.reply_text("Ты уже вошёл в эту комнату.")
        return

    if len(room["players"]) >= room["max_players"]:
        await update.effective_message.reply_text("Комната уже заполнена.")
        return

    if room["game"] == "roulette":
        if len(args) < 2:
            await update.effective_message.reply_text(
                "Для рулетки укажи цвет: красное, чёрное или зеро.\n"
                f"Пример: /join_room {code} чёрное"
            )
            return
        roulette_choice = parse_roulette_choice(args[1])
        if roulette_choice is None:
            await update.effective_message.reply_text("Цвет должен быть: красное, чёрное или зеро.")
            return
        room["choices"][player_id] = roulette_choice

    if not can_pay(player, room["currency"], room["bet_amount"]):
        await update.effective_message.reply_text("Не хватает валюты для ставки.")
        return

    player[room["currency"]] -= room["bet_amount"]
    room["players"].append(player_id)
    save_players()
    save_rooms()

    await update.effective_message.reply_text(
        f"Ты вошёл в комнату {code}.\n"
        f"Игроки: {len(room['players'])}/{room['max_players']}"
    )

    if len(room["players"]) == room["max_players"]:
        result_text = await finish_room_game(context, room)
        await update.effective_message.reply_text(result_text, parse_mode=ParseMode.HTML)


async def rooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        active_rooms_text(chat_id(update)),
        parse_mode=ParseMode.HTML,
    )


async def leave_room(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player_id = user_id(update)
    get_player(player_id, display_name(update))

    for room in ROOMS.values():
        if player_id in room["players"] and room["status"] == "waiting":
            room["players"].remove(player_id)
            PLAYERS[player_id][room["currency"]] += room["bet_amount"]
            if player_id in room["choices"]:
                del room["choices"][player_id]

            if not room["players"]:
                del ROOMS[room["code"]]

            save_players()
            save_rooms()
            await update.effective_message.reply_text("Ты вышел из комнаты, ставка возвращена.")
            return

    await update.effective_message.reply_text("Нет комнаты, из которой можно выйти.")


async def finish_room_game(context: ContextTypes.DEFAULT_TYPE, room: dict[str, Any]) -> str:
    room["status"] = "started"
    room["started_at"] = now_iso()
    game = room["game"]
    currency = room["currency"]
    bet_amount = room["bet_amount"]
    total_bank = bet_amount * len(room["players"])

    if game == "dice":
        for player_id in room["players"]:
            room["results"][player_id] = random.randint(1, 6)
        max_score = max(room["results"].values())
        winner_ids = [player_id for player_id, score in room["results"].items() if score == max_score]
        result_lines = ["🎲 <b>Игра с друзьями: Кубик</b>"]
        for player_id in room["players"]:
            result_lines.append(f"{PLAYERS[player_id]['name']}: {room['results'][player_id]}")

    elif game == "slots":
        for player_id in room["players"]:
            symbols = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
            score = slot_score(symbols)
            room["results"][player_id] = {
                "symbols": symbols,
                "score": score,
            }
        max_score = max(result["score"] for result in room["results"].values())
        winner_ids = [
            player_id for player_id, result in room["results"].items() if result["score"] == max_score
        ]
        result_lines = ["🎰 <b>Игра с друзьями: Слоты</b>"]
        for player_id in room["players"]:
            result = room["results"][player_id]
            result_lines.append(
                f"{PLAYERS[player_id]['name']}: {' '.join(result['symbols'])} — {result['score']} очков"
            )

    else:
        roulette_result = random.choice(["red", "black", "zero"])
        room["results"]["roulette"] = roulette_result
        winner_ids = [
            player_id
            for player_id in room["players"]
            if room["choices"].get(player_id) == roulette_result
        ]
        result_lines = ["🎡 <b>Игра с друзьями: Рулетка</b>"]
        result_lines.append(f"Выпало: {ROULETTE_TITLES[roulette_result]}")
        for player_id in room["players"]:
            choice = room["choices"].get(player_id, "")
            result_lines.append(f"{PLAYERS[player_id]['name']}: {ROULETTE_TITLES.get(choice, choice)}")

        if not winner_ids and ROOM_SETTINGS.get("return_if_no_winner", True):
            for player_id in room["players"]:
                PLAYERS[player_id][currency] += bet_amount
                add_history(
                    player_id,
                    "friend_game",
                    f"Рулетка, комната {room['code']}",
                    "возврат",
                    currency,
                    bet_amount,
                    bet_amount,
                )
            room["status"] = "finished"
            room["finished_at"] = now_iso()
            save_players()
            save_rooms()
            result_lines.append("\nНикто не угадал. Ставки возвращены игрокам.")
            return "\n".join(result_lines)

    payouts_by_player = split_evenly(total_bank, winner_ids)
    base_payout = total_bank // len(winner_ids)

    for winner_id, payout_amount in payouts_by_player.items():
        PLAYERS[winner_id][currency] += payout_amount

    for player_id in room["players"]:
        did_win = player_id in winner_ids
        add_history(
            player_id,
            "friend_game",
            f"{GAME_TITLES[game]}, комната {room['code']}",
            "выигрыш" if did_win else "поражение",
            currency,
            bet_amount,
            payouts_by_player.get(player_id, 0),
        )

    room["status"] = "finished"
    room["finished_at"] = now_iso()
    save_players()
    save_rooms()

    winner_names = ", ".join(PLAYERS[player_id]["name"] for player_id in winner_ids)
    result_lines.append("")
    result_lines.append(f"Победители: <b>{winner_names}</b>")
    result_lines.append(f"Банк: {total_bank} {currency_title(currency)}")
    result_lines.append(f"Выплата победителю: от {base_payout} {currency_title(currency)}")

    for player_id in room["players"]:
        if player_id == room["creator"]:
            continue
        try:
            await context.bot.send_message(
                chat_id=int(player_id),
                text="\n".join(result_lines),
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            continue

    return "\n".join(result_lines)


def slot_score(symbols: list[str]) -> int:
    if symbols == ["7", "7", "7"]:
        return 200
    if symbols == ["💎", "💎", "💎"]:
        return 150
    if len(set(symbols)) == 1:
        return 100
    if len(set(symbols)) == 2:
        return 40
    return 10


def split_evenly(total_amount: int, player_ids: list[str]) -> dict[str, int]:
    payout = total_amount // len(player_ids)
    remainder = total_amount % len(player_ids)
    result: dict[str, int] = {}
    for index, player_id in enumerate(player_ids):
        result[player_id] = payout + (1 if index < remainder else 0)
    return result


def split_proportionally(total_amount: int, bets: list[dict[str, Any]]) -> dict[str, int]:
    total_winner_bet = sum(bet["amount"] for bet in bets)
    raw_payouts = []

    for bet in bets:
        exact_value = total_amount * bet["amount"] / total_winner_bet
        integer_part = int(exact_value)
        raw_payouts.append(
            {
                "player_id": bet["player_id"],
                "payout": integer_part,
                "fraction": exact_value - integer_part,
            }
        )

    paid = sum(item["payout"] for item in raw_payouts)
    remainder = total_amount - paid
    raw_payouts.sort(key=lambda item: item["fraction"], reverse=True)

    for index in range(remainder):
        raw_payouts[index]["payout"] += 1

    return {item["player_id"]: item["payout"] for item in raw_payouts}


async def create_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player_id = user_id(update)
    get_player(player_id, display_name(update))

    if not require_admin(update):
        await update.effective_message.reply_text("Эта команда доступна только админу.")
        return

    raw_text = update.effective_message.text or ""
    payload = raw_text.replace("/create_event", "", 1).strip()
    parts = [part.strip() for part in payload.split("|") if part.strip()]
    if len(parts) < 3:
        await update.effective_message.reply_text(
            "Формат:\n"
            "/create_event Название события | Вариант 1 | Вариант 2 | Вариант 3"
        )
        return

    event_id = str(max([int(key) for key in EVENTS.keys() if key.isdigit()] + [0]) + 1)
    EVENTS[event_id] = {
        "event_id": event_id,
        "title": parts[0],
        "options": parts[1:],
        "status": "open",
        "created_by": player_id,
        "chat_id": chat_id(update),
        "chat_type": update.effective_chat.type if update.effective_chat else "private",
        "currency": "any",
        "minimum_bet": 10,
        "maximum_bet": 5000,
        "bets": {},
        "payouts": [],
        "winner_option": None,
        "created_at": now_iso(),
        "closed_at": None,
        "finished_at": None,
    }
    save_events()
    await update.effective_message.reply_text(f"Событие создано. ID: {event_id}")


async def close_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not require_admin(update):
        await update.effective_message.reply_text("Эта команда доступна только админу.")
        return
    if not context.args:
        await update.effective_message.reply_text("Формат: /close_event event_id")
        return

    event = EVENTS.get(context.args[0])
    if event is None:
        await update.effective_message.reply_text("Событие не найдено.")
        return
    if event["status"] != "open":
        await update.effective_message.reply_text("Закрыть можно только открытое событие.")
        return

    event["status"] = "closed"
    event["closed_at"] = now_iso()
    save_events()
    await update.effective_message.reply_text("Событие закрыто для новых ставок.")


async def cancel_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not require_admin(update):
        await update.effective_message.reply_text("Эта команда доступна только админу.")
        return
    if not context.args:
        await update.effective_message.reply_text("Формат: /cancel_event event_id")
        return

    event = EVENTS.get(context.args[0])
    if event is None:
        await update.effective_message.reply_text("Событие не найдено.")
        return
    if event["status"] == "finished":
        await update.effective_message.reply_text("Нельзя отменить уже завершённое событие.")
        return
    if event["status"] == "cancelled":
        await update.effective_message.reply_text("Событие уже отменено.")
        return

    if EVENT_SETTINGS.get("return_bets_on_cancel", True):
        for bet in event["bets"].values():
            player_id = bet["player_id"]
            PLAYERS[player_id][bet["currency"]] += bet["amount"]
            add_history(
                player_id,
                "event",
                event["title"],
                "возврат",
                bet["currency"],
                bet["amount"],
                bet["amount"],
            )

    event["status"] = "cancelled"
    event["finished_at"] = now_iso()
    save_players()
    save_events()
    await update.effective_message.reply_text("Событие отменено. Ставки возвращены по настройкам.")


async def finish_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not require_admin(update):
        await update.effective_message.reply_text("Эта команда доступна только админу.")
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text("Формат: /finish_event event_id winner_option_number")
        return

    event = EVENTS.get(context.args[0])
    if event is None:
        await update.effective_message.reply_text("Событие не найдено.")
        return
    if event["status"] == "finished":
        await update.effective_message.reply_text("Событие уже завершено.")
        return
    if event["status"] == "cancelled":
        await update.effective_message.reply_text("Нельзя завершить отменённое событие.")
        return

    try:
        winner_option = int(context.args[1]) - 1
    except ValueError:
        await update.effective_message.reply_text("Номер победившего варианта должен быть числом.")
        return

    if winner_option < 0 or winner_option >= len(event["options"]):
        await update.effective_message.reply_text("Такого варианта ответа нет.")
        return

    payout_summary = finish_event_payouts(event, winner_option)
    event["status"] = "finished"
    event["winner_option"] = winner_option
    event["finished_at"] = now_iso()
    save_players()
    save_events()

    await notify_event_players(context, event, winner_option)
    await notify_event_chat(context, event, winner_option)
    await update.effective_message.reply_text(payout_summary)


def finish_event_payouts(event: dict[str, Any], winner_option: int) -> str:
    bets_by_currency: dict[str, list[dict[str, Any]]] = {TOMIKI: [], HOPIKI: []}
    for bet in event["bets"].values():
        bets_by_currency[bet["currency"]].append(bet)

    lines = [
        f"📢 Событие завершено!",
        f"Событие: {event['title']}",
        f"Победил вариант: {event['options'][winner_option]}",
    ]

    for currency, bets in bets_by_currency.items():
        if not bets:
            continue

        total_bank = sum(bet["amount"] for bet in bets)
        winner_bets = [bet for bet in bets if bet["option_index"] == winner_option]
        winner_total = sum(bet["amount"] for bet in winner_bets)

        lines.append(f"\n{currency_title(currency)}")
        lines.append(f"Общий банк: {total_bank}")

        if winner_total <= 0:
            if EVENT_SETTINGS.get("return_bets_if_no_winner", True):
                for bet in bets:
                    PLAYERS[bet["player_id"]][currency] += bet["amount"]
                    record_event_result(event, bet, "возврат", bet["amount"])
                lines.append("Победителей нет. Ставки возвращены.")
            else:
                for bet in bets:
                    record_event_result(event, bet, "поражение", 0)
                lines.append("Победителей нет. Банк остаётся у бота.")
            continue

        proportional_payouts = split_proportionally(total_bank, winner_bets)

        for bet in bets:
            if bet["option_index"] == winner_option:
                payout = proportional_payouts[bet["player_id"]]
                PLAYERS[bet["player_id"]][currency] += payout
                record_event_result(event, bet, "выигрыш", payout)
            else:
                record_event_result(event, bet, "поражение", 0)

        lines.append(f"Сумма победных ставок: {winner_total}")
        lines.append("Выплаты рассчитаны пропорционально ставкам.")

    return "\n".join(lines)


def record_event_result(
    event: dict[str, Any],
    bet: dict[str, Any],
    result: str,
    payout_amount: int,
) -> None:
    payout = {
        "player_id": bet["player_id"],
        "currency": bet["currency"],
        "bet_amount": bet["amount"],
        "payout_amount": payout_amount,
        "result": result,
        "created_at": now_iso(),
    }
    event.setdefault("payouts", []).append(payout)
    add_history(
        bet["player_id"],
        "event",
        event["title"],
        result,
        bet["currency"],
        bet["amount"],
        payout_amount,
    )


async def notify_event_players(
    context: ContextTypes.DEFAULT_TYPE,
    event: dict[str, Any],
    winner_option: int,
) -> None:
    for bet in event["bets"].values():
        player_id = bet["player_id"]
        latest_result = "поражение"
        latest_payout = 0
        for payout in reversed(event.get("payouts", [])):
            if payout["player_id"] == player_id:
                latest_result = payout["result"]
                latest_payout = payout["payout_amount"]
                break
        try:
            await context.bot.send_message(
                chat_id=int(player_id),
                text=(
                    "📢 Событие завершено!\n"
                    f"Событие: {event['title']}\n"
                    f"Победил вариант: {event['options'][winner_option]}\n"
                    f"Твой результат: {latest_result}\n"
                    f"Получено: {latest_payout} {currency_title(bet['currency'])}"
                ),
            )
        except TelegramError:
            continue


async def notify_event_chat(
    context: ContextTypes.DEFAULT_TYPE,
    event: dict[str, Any],
    winner_option: int,
) -> None:
    target_chat_id = event.get("chat_id")
    if not target_chat_id or event.get("chat_type") not in {"group", "supergroup"}:
        return

    try:
        await context.bot.send_message(
            chat_id=int(target_chat_id),
            text=(
                "📢 Событие завершено!\n"
                f"Событие: {event['title']}\n"
                f"Победил вариант: {event['options'][winner_option]}\n"
                f"Всего ставок: {len(event['bets'])}\n"
                "Личные результаты записаны в историю ставок игроков."
            ),
        )
    except TelegramError:
        return


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    open_events = [event for event in EVENTS.values() if event["status"] == "open"]
    if not open_events:
        await update.effective_message.reply_text("Сейчас нет открытых событий.")
        return

    lines = ["📢 Открытые события:"]
    for event in open_events:
        lines.append(event_short_text(event))
    await update.effective_message.reply_text("\n\n".join(lines))


async def event_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Формат: /event event_id")
        return
    event = EVENTS.get(context.args[0])
    if event is None:
        await update.effective_message.reply_text("Событие не найдено.")
        return
    await update.effective_message.reply_text(event_full_text(event))


def event_short_text(event: dict[str, Any]) -> str:
    return (
        f"ID: {event['event_id']}\n"
        f"{event['title']}\n"
        f"Ставка: от {event['minimum_bet']} до {event['maximum_bet']}\n"
        f"Команда: /bet_event {event['event_id']} номер_варианта tomiki сумма"
    )


def event_full_text(event: dict[str, Any]) -> str:
    options = "\n".join(
        f"{index + 1}. {option}" for index, option in enumerate(event["options"])
    )
    return (
        f"📢 Событие #{event['event_id']}\n"
        f"{event['title']}\n\n"
        f"Статус: {event['status']}\n"
        f"Варианты:\n{options}\n\n"
        f"Ставка: от {event['minimum_bet']} до {event['maximum_bet']}\n"
        f"Всего ставок: {len(event['bets'])}\n\n"
        f"Поставить: /bet_event {event['event_id']} номер_варианта tomiki сумма"
    )


async def bet_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player_id = user_id(update)
    player = get_player(player_id, display_name(update))
    if len(context.args) < 4:
        await update.effective_message.reply_text(
            "Формат:\n/bet_event event_id номер_варианта tomiki сумма\n\n"
            "Пример:\n/bet_event 1 2 tomiki 100"
        )
        return

    event = EVENTS.get(context.args[0])
    if event is None:
        await update.effective_message.reply_text("Событие не найдено.")
        return
    if event["status"] != "open":
        await update.effective_message.reply_text("Нельзя поставить на закрытое событие.")
        return

    try:
        option_index = int(context.args[1]) - 1
        amount = int(context.args[3])
    except ValueError:
        await update.effective_message.reply_text("Номер варианта и сумма должны быть числами.")
        return

    currency = parse_currency(context.args[2])
    if currency is None:
        await update.effective_message.reply_text("Валюта должна быть: tomiki или hopiki.")
        return

    if option_index < 0 or option_index >= len(event["options"]):
        await update.effective_message.reply_text("Такого варианта ответа нет.")
        return
    if amount <= 0:
        await update.effective_message.reply_text("Нельзя поставить отрицательную или нулевую сумму.")
        return
    if amount < event["minimum_bet"]:
        await update.effective_message.reply_text("Ставка меньше минимальной.")
        return
    if amount > event["maximum_bet"]:
        await update.effective_message.reply_text("Ставка больше максимальной.")
        return
    if event["currency"] != "any" and event["currency"] != currency:
        await update.effective_message.reply_text("Для этого события выбрана другая валюта.")
        return
    if player_id in event["bets"] and not EVENT_SETTINGS.get("allow_change_bet", False):
        await update.effective_message.reply_text("Ты уже ставил на это событие.")
        return
    if not can_pay(player, currency, amount):
        await update.effective_message.reply_text("Не хватает валюты для ставки.")
        return

    if player_id in event["bets"] and EVENT_SETTINGS.get("allow_change_bet", False):
        old_bet = event["bets"][player_id]
        PLAYERS[player_id][old_bet["currency"]] += old_bet["amount"]

    player[currency] -= amount
    event["bets"][player_id] = {
        "player_id": player_id,
        "player_name": player["name"],
        "option_index": option_index,
        "option_title": event["options"][option_index],
        "currency": currency,
        "amount": amount,
        "created_at": now_iso(),
    }
    save_players()
    save_events()

    await update.effective_message.reply_text(
        f"Ставка принята!\n"
        f"Событие: {event['title']}\n"
        f"Вариант: {event['options'][option_index]}\n"
        f"Сумма: {amount} {currency_title(currency)}"
    )


async def bet_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = get_player(user_id(update), display_name(update))
    history = player.get("bet_history", [])
    if not history:
        await update.effective_message.reply_text("История ставок пока пустая.")
        return

    lines = ["📜 История ставок:"]
    for item in history[-10:]:
        lines.append(
            f"\n{item['date']}\n"
            f"{item['title']}\n"
            f"Результат: {item['result']}\n"
            f"Ставка: {item['bet_amount']} {currency_title(item['currency'])}\n"
            f"Получено: {item['payout_amount']} {currency_title(item['currency'])}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    get_player(user_id(update), display_name(update))
    await update.effective_message.reply_text(shop_text())


def shop_text() -> str:
    lines = ["🛍 Магазин безделушек:"]
    for item_id, item in SHOP_ITEMS.items():
        lines.append(
            f"\n{item_id}. {item['name']}\n"
            f"{item['description']}\n"
            f"Цена: {item['price']} {currency_title(item['currency'])}\n"
            f"Купить: /buy_item {item_id}"
        )
    return "\n".join(lines)


async def buy_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player_id = user_id(update)
    player = get_player(player_id, display_name(update))
    if not context.args:
        await update.effective_message.reply_text("Формат: /buy_item item_id\nПосмотреть предметы: /shop")
        return

    item_id = context.args[0]
    item = SHOP_ITEMS.get(item_id)
    if item is None:
        await update.effective_message.reply_text("Такого предмета нет. Посмотри список: /shop")
        return

    currency = item["currency"]
    price = item["price"]
    if not can_pay(player, currency, price):
        await update.effective_message.reply_text(
            f"Не хватает валюты. Нужно {price} {currency_title(currency)}."
        )
        return

    player[currency] -= price
    player.setdefault("items", []).append(
        {
            "item_id": item_id,
            "name": item["name"],
            "description": item["description"],
            "currency": currency,
            "price": price,
            "bought_at": now_iso(),
        }
    )
    save_players()

    await update.effective_message.reply_text(
        f"Покупка готова!\n"
        f"Предмет: {item['name']}\n"
        f"Списано: {price} {currency_title(currency)}\n"
        f"Баланс: {player[currency]} {currency_title(currency)}"
    )


async def inventory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = get_player(user_id(update), display_name(update))
    items = player.get("items", [])
    if not items:
        await update.effective_message.reply_text("Инвентарь пустой. Посмотри безделушки в /shop.")
        return

    lines = ["🎒 Инвентарь:"]
    for index, item in enumerate(items[-20:], start=1):
        if isinstance(item, dict):
            lines.append(f"{index}. {item.get('name', 'Предмет')}")
        else:
            lines.append(f"{index}. {item}")
    await update.effective_message.reply_text("\n".join(lines))


async def give_tomiki(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await give_currency(update, context, TOMIKI)


async def give_hopiki(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await give_currency(update, context, HOPIKI)


async def give_currency(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str) -> None:
    if not require_admin(update):
        await update.effective_message.reply_text("Эта команда доступна только админу.")
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text(f"Формат: /give_{currency} user_id amount")
        return
    try:
        target_id = str(int(context.args[0]))
        amount = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("user_id и amount должны быть числами.")
        return
    if amount <= 0:
        await update.effective_message.reply_text("Сумма должна быть больше нуля.")
        return

    target = get_player(target_id, f"Игрок {target_id}")
    target[currency] += amount
    save_players()
    await update.effective_message.reply_text(
        f"Выдано {amount} {currency_title(currency)} игроку {target_id}."
    )


async def give_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not require_admin(update):
        await update.effective_message.reply_text("Эта команда доступна только админу.")
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text("Формат: /give_item user_id название_предмета")
        return
    target_id = context.args[0]
    item_name = " ".join(context.args[1:]).strip()
    target = get_player(target_id, f"Игрок {target_id}")
    target.setdefault("items", []).append(
        {
            "name": item_name,
            "created_at": now_iso(),
        }
    )
    save_players()
    await update.effective_message.reply_text(f"Предмет выдан игроку {target_id}: {item_name}")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not require_admin(update):
        await update.effective_message.reply_text("Эта команда доступна только админу.")
        return
    await update.effective_message.reply_text(stats_text())


async def group_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_group_chat(update) or update.effective_message is None:
        return

    raw_text = update.effective_message.text or ""
    text = raw_text.strip().lower()
    if not text:
        return

    get_player(user_id(update), display_name(update))

    if text in {"помощь", "команды", "help", "меню"}:
        await help_command(update, context)
        return
    if text in {"баланс", "мой баланс", "профиль", "balance"}:
        await balance(update, context)
        return
    if text in {"история", "история ставок"}:
        await bet_history(update, context)
        return
    if text in {"магазин", "shop"}:
        await shop(update, context)
        return
    if text in {"инвентарь", "мои предметы", "inventory"}:
        await inventory(update, context)
        return
    if text in {"комнаты", "rooms"}:
        await rooms(update, context)
        return
    if text in {"события", "events"}:
        await events(update, context)
        return

    parts = text.split()
    command = parts[0]

    if command in {"кубик", "dice"}:
        await handle_group_dice_text(update, parts)
        return
    if command in {"слоты", "slots"}:
        await handle_group_slots_text(update, parts)
        return
    if command in {"рулетка", "roulette"}:
        await handle_group_roulette_text(update, parts)
        return
    if command in {"купить", "buy"}:
        await handle_group_buy_text(update, context, parts)


async def handle_group_dice_text(update: Update, parts: list[str]) -> None:
    if len(parts) != 4:
        await update.effective_message.reply_text("Формат: кубик 6 tomiki 100")
        return
    dice_bet = parse_dice_bet(parts[1])
    currency = parse_currency(parts[2])
    try:
        amount = int(parts[3])
    except ValueError:
        await update.effective_message.reply_text("Ставка должна быть числом.")
        return
    await play_solo_game(update, "dice", currency, amount, dice_bet=dice_bet)


async def handle_group_slots_text(update: Update, parts: list[str]) -> None:
    if len(parts) != 3:
        await update.effective_message.reply_text("Формат: слоты tomiki 100")
        return
    currency = parse_currency(parts[1])
    try:
        amount = int(parts[2])
    except ValueError:
        await update.effective_message.reply_text("Ставка должна быть числом.")
        return
    await play_solo_game(update, "slots", currency, amount)


async def handle_group_roulette_text(update: Update, parts: list[str]) -> None:
    if len(parts) != 4:
        await update.effective_message.reply_text("Формат: рулетка красное tomiki 100")
        return
    roulette_choice = parse_roulette_choice(parts[1])
    currency = parse_currency(parts[2])
    try:
        amount = int(parts[3])
    except ValueError:
        await update.effective_message.reply_text("Ставка должна быть числом.")
        return
    await play_solo_game(update, "roulette", currency, amount, roulette_choice)


async def handle_group_buy_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parts: list[str],
) -> None:
    if len(parts) != 2:
        await update.effective_message.reply_text("Формат: купить 1")
        return
    context.args = [parts[1]]
    await buy_item(update, context)


def stats_text() -> str:
    active_rooms = len([room for room in ROOMS.values() if room["status"] == "waiting"])
    open_events = len([event for event in EVENTS.values() if event["status"] == "open"])
    return (
        "🛠 Статистика бота\n"
        f"Игроков: {len(PLAYERS)}\n"
        f"Всего комнат: {len(ROOMS)}\n"
        f"Активных комнат: {active_rooms}\n"
        f"Всего событий: {len(EVENTS)}\n"
        f"Открытых событий: {open_events}"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    player_id = str(query.from_user.id)
    get_player(player_id, query.from_user.full_name)
    data = query.data

    if data == "menu_main":
        await query.edit_message_text("Главное меню:", reply_markup=main_menu(is_admin(player_id)))
    elif data == "menu_solo":
        await query.edit_message_text("🎮 Играть одному", reply_markup=solo_keyboard())
    elif data == "menu_rooms":
        await query.edit_message_text("🤝 Игры с друзьями", reply_markup=rooms_keyboard())
    elif data == "menu_events":
        await query.edit_message_text("📢 События", reply_markup=events_keyboard(is_admin(player_id)))
    elif data == "menu_history":
        history = PLAYERS[player_id].get("bet_history", [])
        if not history:
            await query.edit_message_text("История ставок пока пустая.", reply_markup=main_menu(is_admin(player_id)))
        else:
            lines = ["📜 История ставок:"]
            for item in history[-10:]:
                lines.append(
                    f"\n{item['date']}\n"
                    f"{item['title']}\n"
                    f"Результат: {item['result']}\n"
                    f"Получено: {item['payout_amount']} {currency_title(item['currency'])}"
                )
            await query.edit_message_text("\n".join(lines), reply_markup=main_menu(is_admin(player_id)))
    elif data == "menu_admin":
        if not is_admin(player_id):
            await query.edit_message_text("Админ-панель доступна только админу.")
        else:
            await query.edit_message_text("🛠 Админ-панель", reply_markup=admin_keyboard())
    elif data == "solo_dice_help":
        await query.edit_message_text(
            "Ставка на кубик:\n"
            "/dice 6 tomiki 100\n"
            "/dice больше tomiki 100\n\n"
            "Число 1-6 даёт x6, больше/меньше/чёт/нечёт дают x2.",
            reply_markup=solo_keyboard(),
        )
    elif data == "solo_slots_help":
        await query.edit_message_text(
            "Слоты одному:\n"
            "/slots tomiki 100\n\n"
            "3 семёрки дают x5, 3 алмаза x4, любые 3 одинаковых x3, 2 одинаковых x2.",
            reply_markup=solo_keyboard(),
        )
    elif data == "solo_roulette_help":
        await query.edit_message_text(
            "Рулетка одному:\n"
            "/roulette красное tomiki 100\n\n"
            "Красное и чёрное дают x2, зеро даёт x14.",
            reply_markup=solo_keyboard(),
        )
    elif data == "room_create_help":
        await query.edit_message_text(
            "Создание комнаты:\n"
            "/create_room игра игроки валюта ставка [цвет]\n\n"
            "Примеры:\n"
            "/create_room кубик 3 tomiki 100\n"
            "/create_room слоты 2 hopiki 50\n"
            "/create_room рулетка 4 tomiki 100 красное",
            reply_markup=rooms_keyboard(),
        )
    elif data == "room_join_help":
        await query.edit_message_text(
            "Вход в комнату:\n"
            "/join_room код [цвет]\n\n"
            "Для рулетки цвет обязателен:\n"
            "/join_room AB123 чёрное",
            reply_markup=rooms_keyboard(),
        )
    elif data == "room_list":
        target_chat_id = query.message.chat_id if query.message else None
        await query.edit_message_text(
            active_rooms_text(target_chat_id),
            parse_mode=ParseMode.HTML,
            reply_markup=rooms_keyboard(),
        )
    elif data == "event_list":
        open_events = [event for event in EVENTS.values() if event["status"] == "open"]
        if not open_events:
            await query.edit_message_text("Сейчас нет открытых событий.", reply_markup=events_keyboard(is_admin(player_id)))
        else:
            await query.edit_message_text(
                "\n\n".join(event_short_text(event) for event in open_events),
                reply_markup=events_keyboard(is_admin(player_id)),
            )
    elif data == "event_bet_help":
        await query.edit_message_text(
            "Ставка на событие:\n"
            "/bet_event event_id номер_варианта tomiki сумма\n\n"
            "Пример:\n/bet_event 1 2 hopiki 100",
            reply_markup=events_keyboard(is_admin(player_id)),
        )
    elif data == "event_create_help":
        await query.edit_message_text(
            "Создание события:\n"
            "/create_event Название | Вариант 1 | Вариант 2 | Вариант 3",
            reply_markup=admin_keyboard() if is_admin(player_id) else events_keyboard(False),
        )
    elif data == "admin_event_help":
        await query.edit_message_text(
            "Команды событий:\n"
            "/close_event event_id\n"
            "/finish_event event_id winner_option_number\n"
            "/cancel_event event_id\n"
            "/events\n"
            "/event event_id",
            reply_markup=admin_keyboard(),
        )
    elif data == "admin_give_help":
        await query.edit_message_text(
            "Команды выдачи:\n"
            "/give_tomiki user_id amount\n"
            "/give_hopiki user_id amount\n"
            "/give_item user_id название_предмета",
            reply_markup=admin_keyboard(),
        )
    elif data == "admin_stats":
        if not is_admin(player_id):
            await query.edit_message_text("Админ-панель доступна только админу.")
        else:
            await query.edit_message_text(stats_text(), reply_markup=admin_keyboard())


def build_application() -> Application:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Укажи токен бота в переменной окружения BOT_TOKEN.")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("solo_game", solo_game))
    application.add_handler(CommandHandler("dice", solo_dice))
    application.add_handler(CommandHandler("slots", solo_slots))
    application.add_handler(CommandHandler("roulette", solo_roulette))
    application.add_handler(CommandHandler("create_room", create_room))
    application.add_handler(CommandHandler("join_room", join_room))
    application.add_handler(CommandHandler("rooms", rooms))
    application.add_handler(CommandHandler("leave_room", leave_room))
    application.add_handler(CommandHandler("create_event", create_event))
    application.add_handler(CommandHandler("close_event", close_event))
    application.add_handler(CommandHandler("finish_event", finish_event))
    application.add_handler(CommandHandler("cancel_event", cancel_event))
    application.add_handler(CommandHandler("events", events))
    application.add_handler(CommandHandler("event", event_detail))
    application.add_handler(CommandHandler("bet_event", bet_event))
    application.add_handler(CommandHandler("bet_history", bet_history))
    application.add_handler(CommandHandler("shop", shop))
    application.add_handler(CommandHandler("buy_item", buy_item))
    application.add_handler(CommandHandler("inventory", inventory))
    application.add_handler(CommandHandler("give_tomiki", give_tomiki))
    application.add_handler(CommandHandler("give_hopiki", give_hopiki))
    application.add_handler(CommandHandler("give_item", give_item))
    application.add_handler(CommandHandler("admin_stats", admin_stats))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, group_text_handler))
    return application


def main() -> None:
    load_data()
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
