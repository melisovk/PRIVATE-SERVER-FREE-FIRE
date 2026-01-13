# CREATE MLSV 
# СОЗДАНО В ИСКЛЮЧИТЕЛЬНО РАЗВЛЕКАТЛЕНЫХ ЦЕЛЯХ!
# АВТОРСКИЕ ПРАВА ПРЕНАДЛЕЖАТ GARENA

from flask import Flask, request, jsonify, Response
import sqlite3
import json
import os
import logging
import time
import uuid
import random
import base64
import sys
import re


app = Flask(__name__)
DB_FILE = 'game.db'
CLANS_FILE = "clans.json"

# Глобальная переменная для "запоминания" последнего игрока
# (Решает проблему, когда игра не шлет токен в GetBackpack)
LAST_ACTIVE_TOKEN = None

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

START_CHARACTERS = [
    101000001, # Eve (Nulla / Ева) - Стартовый женский
    102000004, # Adam (Primis / Адам) - Стартовый мужской
    102000002, # Ford (Форд)
    101000002, # Olivia (Оливия)
    102000005, # Andrew (Эндрю)
    101000006, # Kelly (Келли)
    101000007, # Nikita (Никита)
    102000008, # Maxim (Максим)
    102000009, # Miguel (Мигель)
    102000013, # Antonio (Антонио)
]

DEFAULT_CLOTHES = [112000001, 113000001] 

MAIN_CHAR_ID = 101000006

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # Позволяет обращаться к колонкам по имени
    return conn


# Загрузка кланов (если файл не создается, код его создаст)
def load_clans():
    if not os.path.exists(CLANS_FILE):
        with open(CLANS_FILE, "w", encoding='utf-8') as f:
            json.dump({}, f)
        return {}
    try:
        with open(CLANS_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_clans(clans_data):
    try:
        with open(CLANS_FILE, "w", encoding='utf-8') as f:
            json.dump(clans_data, f, indent=4, ensure_ascii=False)
        print("Clans saved successfully.") # Лог для проверки
    except Exception as e:
        print(f"Error saving clans: {e}")

def save_clans(clans_data):
    with open(CLANS_FILE, "w", encoding='utf-8') as f:
        json.dump(clans_data, f, indent=4, ensure_ascii=False)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            account_id INTEGER PRIMARY KEY,
            open_id TEXT UNIQUE,
            token TEXT,
            user_data TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_user_to_db(user):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (account_id, open_id, token, user_data)
        VALUES (?, ?, ?, ?)
    ''', (user['account_id'], user['open_id'], user['token'], json.dumps(user, ensure_ascii=False)))
    conn.commit()
    conn.close()

def get_user_by_token(token):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_data FROM users WHERE token = ?', (token,))
    row = cursor.fetchone()
    conn.close()
    if row: return json.loads(row[0])
    return None

def get_user_by_open_id(open_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_data FROM users WHERE open_id = ?', (open_id,))
    row = cursor.fetchone()
    conn.close()
    if row: return json.loads(row[0])
    return None

def get_next_uid():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(account_id) FROM users")
    row = cursor.fetchone()
    val = row[0]
    conn.close()
    return (val + 1) if val else 10000001

# --- АВТОРИЗАЦИЯ (ИСПРАВЛЕННАЯ) ---
def get_user_from_request():
    global LAST_ACTIVE_TOKEN
    try:
        json_data = request.get_json(force=True, silent=True) or {}
        token = json_data.get('token')
        open_id = json_data.get('open_id')

        user = None

        # 1. Прямой поиск
        if token: user = get_user_by_token(token)
        if not user and open_id: user = get_user_by_open_id(open_id)

        # 2. ФОЛЛБЭК: Если игра забыла прислать токен, берем последний активный
        if not user and LAST_ACTIVE_TOKEN:
            # logger.info(f"Using fallback token: {LAST_ACTIVE_TOKEN}")
            user = get_user_by_token(LAST_ACTIVE_TOKEN)

        if user:
            # Если нашли юзера, обновляем глобальный кэш
            if user.get('token'):
                LAST_ACTIVE_TOKEN = user['token']
            return user
        else:
            logger.error(f"USER NOT FOUND! Payload: {json_data}")
            return None

    except Exception as e:
        logger.error(f"Auth Error: {e}")
        return None

def get_item_type(item_id):
    item_id = int(item_id)
    if 100000000 < item_id < 103000000: return 4 # Персонаж
    return 1 # Предмет

def get_item_type_id(item_id):
    sid = str(item_id)
    # 10x.. или маленькие ID - это Персонажи
    if sid.startswith("101") or sid.startswith("102") or int(item_id) < 200000000:
        return 4 
    # 2xx.. - Одежда
    if sid.startswith("2"): 
        return 1
    # Остальное (оружие и т.д.) - по умолчанию 1 или другой тип
    return 1


# --- ФОРМАТ ОТВЕТА ---
def format_user_response(user):
    # Если в базе нет avatar_id, используем стандартный
    avatar_id = int(user.get('avatar_id', MAIN_CHAR_ID))
    
    raw_clan_id = user.get('clan_id')
    print(f"[DEBUG] format_user_response: clan_id из базы = {raw_clan_id}")

    # Защита: если None или пусто, ставим 0. Иначе берем число.
    final_clan_id = int(raw_clan_id) if raw_clan_id else 0

    return {
        "result": 0,
        "is_new": 0,
        
        # --- Основные идентификаторы ---
        "account_id": int(user['account_id']),
        "uid": int(user['account_id']),
        "open_id": user['open_id'],
        "token": user['token'],
        "nickname": user['nickname'],
        "region": user.get('region', "RU"), # Берет из базы или ставит RU
        
        # --- Данные из HTTP_LoginRes (Берем из базы) ---
        "clan_id": final_clan_id,             # Клан
        "account_type": int(user.get('account_type', 1)),   # Тип аккаунта
        "role": int(user.get('role', 1)),                   # Роль
        "is_emulator": bool(user.get('is_emulator', False)),# Эмулятор
        "has_elite_pass": bool(user.get('has_elite_pass', False)), # Элитный пропуск
        "badge_cnt": int(user.get('badge_cnt', 0)),         # Кол-во значков (у тебя 99)
        "badge_id": int(user.get('badge_id', 0)),           # ID надетого значка
        
        # --- Технические параметры ---
        "noti_region": "RU",
        "notification_channel": "",
        "ttl": 31536000,
        "event_log_url": "",
        "voice_server": 0,
        "chat_server": 56747454,
        "region_id_mapping": [],
        "new_active_region": "RU",
        "recommend_regions": ["RU"],
        "server_time": int(time.time()),
        "queue_position": 0,
        "need_waiting_secs": 0,

        # --- Прогресс и валюта ---
        "create_at": int(user.get('create_at', time.time())),
        "level": int(user.get('level', 1)),       # Уровень (у тебя 99)
        "exp": int(user.get('exp', 0)),           # Опыт
        "coins": int(user.get('coins', 0)),       # Золото
        "gems": int(user.get('gems', 0)),        # Алмазы
        
        # Дубликаты для совместимости старых версий
        "UserCoins": int(user.get('coins', 0)),
        "UserGems": int(user.get('gems', 0)),
        "head_pic": avatar_id,
        "avatar_id": avatar_id,
        
        # --- Профиль персонажа ---
        "user_profile": {
            "avatar_id": avatar_id,
            "skill_id": int(user.get('skill_id', 0)), # Навык из базы
            "item_id": START_CHARACTERS,
            "clothes": DEFAULT_CLOTHES,
            "skin_color": 0,
            "unlocked_level": int(user.get('level', 1)) # Разблокированный уровень
        },
        "EquipInfo": {
            "AvatarID": avatar_id,
            "WeaponID": 0,
            "SetID": DEFAULT_CLOTHES
        }
    }



# ==========================================
# AUTH
# ==========================================

@app.route('/PlatformLogin', methods=['POST'])
def platform_login():
    global LAST_ACTIVE_TOKEN
    try:
        json_data = request.get_json(force=True, silent=True) or {}
        token = json_data.get('login_token') 
        open_id = json_data.get('open_id')

        user = None
        if open_id: user = get_user_by_open_id(open_id)
        elif token: user = get_user_by_token(token)

        if user:
            new_token = uuid.uuid4().hex
            user['token'] = new_token
            LAST_ACTIVE_TOKEN = new_token # Запоминаем сессию

            save_user_to_db(user)
            logger.info(f"[LOGIN] Success: {user['nickname']}")
            return jsonify(format_user_response(user))

        logger.warning(f"[LOGIN] Fail for {open_id}. Triggering Register.")
        return jsonify({"result": 1, "msg": "User not found"}), 404
    except Exception as e:
        logger.error(f"Login Error: {e}")
        return jsonify({'error': 'Error'}), 500

@app.route('/PlatformRegister', methods=['POST'])
def platform_register():
    global LAST_ACTIVE_TOKEN
    try:
        json_data = request.get_json(force=True, silent=True) or {}
        open_id = json_data.get('open_id')
        nickname = json_data.get('nickname', 'Player')

        new_uid = get_next_uid()
        new_token = uuid.uuid4().hex

        inventory = []
        added_ids = set() # Чтобы не добавлять дубликаты

        # --- 1. ДОБАВЛЯЕМ ПЕРСОНАЖЕЙ ---
        # (Предполагаем, что START_CHARACTERS и MAIN_CHAR_ID определены выше в коде)
        for char_id in START_CHARACTERS:
            is_equip = 1 if char_id == MAIN_CHAR_ID else 0
            inventory.append({"iID": char_id, "equip": is_equip})
            added_ids.add(char_id)

        # --- 2. ГЕНЕРАЦИЯ ВСЕХ ВЕЩЕЙ (UNLOCK ALL) ---
        # Диапазоны ID для версии 1.22.1
        all_items_ranges = [
            (201000001, 150), # 🧢 Шапки / Маски
            (202000001, 100), # 🕶️ Очки
            (203000001, 300), # 👕 Майки
            (204000001, 250), # 👖 Штаны
            (205000001, 150), # 👟 Обувь
            (210000001, 60),  # 📦 Сеты
            (401000001, 50),  # 🎒 Рюкзаки
            (402000001, 30),  # 📦 Лутбоксы
            (403000001, 50),  # 🪂 Парашюты
            (404000001, 50),  # 🏄 Доски
            (901000001, 100), # 🔫 Оружие
        ]

        # Проходимся по диапазонам и добавляем вещи
        for start_id, count in all_items_ranges:
            for i in range(count):
                item_id = start_id + i

                if item_id in added_ids:
                    continue # Пропускаем, если уже есть (например, персонаж)

                # Проверяем, нужно ли надеть этот предмет (если он в стартовом наборе)
                is_equip = 0
                if item_id in DEFAULT_CLOTHES:
                    is_equip = 1

                inventory.append({"iID": item_id, "equip": is_equip})
                added_ids.add(item_id)
                
                simple_ids_list = [item['iID'] for item in inventory]

        # --- СОБИРАЕМ ДАННЫЕ ЮЗЕРА ---
        user_data = {
            'account_id': new_uid,
            'open_id': open_id,
            'token': new_token,
            'nickname': nickname,
            'level': 10,              # Уровень 10
            'exp': 1000,
            'coins': 999999,          # Много денег
            'gems': 999999,           # Много алмазов
            'avatar_id': MAIN_CHAR_ID if 'MAIN_CHAR_ID' in globals() else 101000006,
            'inventory': inventory,
            'create_at': int(time.time()),

            # --- Доп поля ---
            'clan_id': 0,
            'region': "RU",
            'account_type': 1,
            'role': 1,
            'has_elite_pass': True,
            'is_emulator': False,
            'badge_cnt': 100,
            'badge_id': 1001000001,
            'gender': 1,
            'liked': 100,
            'skill_id': 0,
            # Дублируем инвентарь в items_id на всякий случай (некоторые версии просят)
            'items_id': simple_ids_list, 
            'items_ids': simple_ids_list
        }

        LAST_ACTIVE_TOKEN = new_token
        save_user_to_db(user_data)

        print(f"[REGISTER] Создан игрок: {nickname} (ID: {new_uid}). Выдано предметов: {len(inventory)}")

        resp = format_user_response(user_data)
        resp['is_new'] = 1
        return jsonify(resp)

    except Exception as e:
        # Используем print, если logger не настроен, или logger.error
        print(f"[Register Error] {e}") 
        return jsonify({'error': 'Error'}), 500



# ==========================================
# GAMEPLAY
# ==========================================

@app.route('/GetPlatformProfile', methods=['POST'])
def get_platform_profile():
    try:
        user = get_user_from_request()
        if not user:
             return jsonify({"result": 1})

        av_id = int(user.get('avatar_id', MAIN_CHAR_ID))

        # --- ВАЖНО: Собираем список всех ID предметов ---
        # Игра сверяет этот список, чтобы убрать замки в меню
        inventory_ids = [int(item['iID']) for item in user.get('inventory', [])]

        return jsonify({
            "result": 0,
            "account_id": int(user['account_id']),
            "nickname": user['nickname'],
            "level": int(user.get('level', 10)),
            "clan_id": int(user.get('clan_id', 0)),   
            "UserCoins": int(user.get('coins', 99999)),
            "UserGems": int(user.get('gems', 99999)),
            "head_pic": av_id,
            "avatar_id": av_id,

            # !!! ЭТО УБИРАЕТ ЗАМКИ В ПРОФИЛЕ !!!
            "items": inventory_ids,
            "items_id": inventory_ids,

            "clothes": DEFAULT_CLOTHES # То, что надето сейчас
        })
    except Exception as e:
        print(f"Error GetPlatformProfile: {e}")
        return jsonify({"result": 1})

@app.route('/GetProfiles', methods=['POST'])
def get_profiles():
    user = get_user_from_request()
    profiles = []

    if user:
        cur_av = int(user.get('avatar_id', MAIN_CHAR_ID))

        # Проходим по инвентарю и ищем персонажей
        # ID персонажей всегда начинаются на 101... (жен) или 102... (муж)
        for item in user.get('inventory', []):
            i_id = int(item['iID'])

            # Проверка: Это персонаж? (ID меньше 103000000)
            if 100000000 < i_id < 103000000:
                profiles.append({
                    "avatar_id": i_id,
                    "level": 6,              # Уровень персонажа
                    "unlocked_level": 6,
                    "exp": 1000,
                    "clan_id": 0,
                    "skill_id": 0, 
                    "slot_count": 3,         # Слоты навыков
                    "equiped_skills": [],
                    "skin_id": 0, 
                    "skin_color": 0,
                    "clothes": DEFAULT_CLOTHES, # Одежда на персонаже
                    "is_selected": (i_id == cur_av),
                    "is_trial": False
                })

    # Если список пуст, игра покажет замки. Мы должны что-то вернуть.
    print(f"[GetProfiles] Найдено {len(profiles)} персонажей.")
    return jsonify({"result": 0, "profiles": profiles})


@app.route('/GetUnlockProfileInfo', methods=['POST'])
def get_unlock_info():
    user = get_user_from_request()
    unlocked = []

    if user:
        # Проходимся по инвентарю
        for item in user.get('inventory', []):
            unlocked.append({
                "item_id": int(item['iID']), 
                "end_time": -1,         # -1 означает "навсегда"
                "is_permanent": 1       # Доп. флаг
            })

    # Также можно принудительно добавить стартовых персонажей, если их нет
    return jsonify({
        "result": 0, 
        "unlocked_item_list": unlocked
    })

    
    
@app.route('/GetScrollMarquee', methods=['POST'])
def get_scroll_marquee():
    try:
        json_data = request.get_json(force=True, silent=True) or {}
        
        # 1. Считываем, какой язык и регион хочет клиент
        # Если клиент не прислал, ставим дефолт
        req_lang = json_data.get('lang_name', 'ru') 
        req_region = json_data.get('region', 'RU')

        now = int(time.time())

        # 2. Формируем очередь сообщений
        # Добавляем два сообщения, чтобы строка "ехала" дольше
        
        msgs = [
            {
                "content": "ДОБРО ПОАЖЛОВАТЬ НА ПРИВАТНЫЙ СЕРВЕР",
                "language": req_lang,  # Возвращаем тот же язык, что просил клиент
                "region": req_region,  # Возвращаем тот же регион
                "order_in_this_language": 1, # Первое
                "start_time": now - 100000,
                "end_time": now + 1000000
            },
            {
                "content": "ПОДПИСЫВАЙТЕСЬ НА ТЕЛЕГРАМ КАНАЛ!",
                "language": req_lang,
                "region": req_region,
                "order_in_this_language": 2, # Второе (продлевает показ)
                "start_time": now - 100000,
                "end_time": now + 1000000
            }
        ]

        response = {
            "result": 0,
            "scrollMarquees": msgs
        }
        
        logger.info(f"[GetScrollMarquee] Sent messages for lang: {req_lang}")
        return jsonify(response)

    except Exception as e:
        logger.error(f"[GetScrollMarquee] Error: {e}")
        return jsonify({"result": 0, "scrollMarquees": []})


@app.route('/GetSplashBanner', methods=['POST'])
def get_splash_banner():
    try:
        # Можно получить язык, если нужно разные баннеры
        # json_data = request.get_json(force=True, silent=True) or {}
        # lang = json_data.get('language', 'en')

        banners = [
            {
                "id": 1,                    # ID баннера
                "name": "Welcome",          # Название
                "sort_id": 1,               # Порядок сортировки (1 - первый)
                
                # Ссылка на картинку (должна быть доступна из интернета!)
                # Я поставил генератор картинок для теста
                "image_url": "https://i.pinimg.com/originals/c5/a6/a7/c5a6a7123f26730ee4e375ea70d3c4e2.jpg", 
                
                "gos_pos": 1,               # Тип действия (обычно 0 - ничего, 1 - открыть ссылку)
                "gos_url": "https://t.me/freefireoldver"  # Ссылка, куда перекинет игрока при нажатии
            },
            {
                "id": 2,
                "name": "News",
                "sort_id": 2,
                "image_url": "https://avatars.mds.yandex.net/i?id=6bfa1d57f3e6487cdb48e2426080e5fa_l-3569687-images-thumbs&n=13", 
                "gos_pos": 1,               # 0 - просто картинка, не кликабельная
                "gos_url": ""
            }
        ]

        response = {
            "result": 0,
            "splashBanners": banners  # Точно как в C# (HTTP_SplashBannerDataRes)
        }
        
        logger.info(f"[GetSplashBanner] Sent {len(banners)} banners")
        return jsonify(response)

    except Exception as e:
        logger.error(f"[GetSplashBanner] Error: {e}")
        return jsonify({"result": 0, "splashBanners": []})

    except Exception as e:
        logger.error(f"[GetPlayerPersonalShow] Error: {e}")
        return jsonify({"result": 0})






@app.route('/GetPlayerPersonalShow', methods=['POST'])
def get_player_personal_show():
    try:
        user = get_user_from_request()
        if not user:
            return jsonify({"result": 1})

        # Получаем ID аватара и одежду
        avatar_id = int(user.get('avatar_id', 101000006))
        # Важно: тут лучше брать реальную надетую одежду, пока ставим дефолт
        clothes = DEFAULT_CLOTHES 

        response = {
            "result": 0,
            
            # 1. basic_info (AccountInfoBasic) — Основная инфа
            "basic_info": {
                "account_id": int(user['account_id']),
                "nickname": user['nickname'],
                "region": "RU",
                "level": int(user.get('level', 1)),
                "rank": int(user.get('rank', 19)),         # Ранг в КБ
                "ranking_points": 10000,
                "badge_cnt": int(user.get('badge_cnt', 1)), # Значки пропуска
                'badge_id': 1001000001,
                "liked": int(user.get('liked', 2)),      # Лайки
                "exp": int(user.get('exp', 0)),
                "max_exp": 1000,
            },

            # 2. profile_info (AvatarProfile) — Внешний вид
            "profile_info": {
                "avatar_id": avatar_id,
                "clothes": clothes,      # Список ID надетой одежды
            },

            "history_ep_info": [],   # BasicEPInfo (История пропусков)
        }

        return jsonify(response)

    except Exception as e:
        logger.error(f"[GetPlayerPersonalShow] Error: {e}")
        return jsonify({"result": 0})




# --- СТАТИСТИКА ---

@app.route('/GetPlayerStats', methods=['POST'])
def get_player_stats():
    try:
        user = get_user_from_request()

        # --- ИСПРАВЛЕНИЕ ЗАВИСАНИЯ ---
        # Версия 1.22.1 ждет статистику по режимам "0" (Соло), "1" (Дуо), "2" (Сквад).
        # Мы создаем "нулевую" статистику.

        empty_mode_stats = {
            "matches": 0, 
            "wins": 0, 
            "kills": 0, 
            "headshots": 0, 
            "damage": 0
        }

        stats_structure = {
            "0": empty_mode_stats,
            "1": empty_mode_stats,
            "2": empty_mode_stats
        }

        # Превращаем в строку JSON
        detailed_json = json.dumps(stats_structure)

        return jsonify({
            "result": 0,
            "mmr": 0,
            "games_played": 0,
            "wins": 0,
            "kills": 0,
            "detailed_stats": detailed_json # Теперь тут корректная структура
        })
    except Exception as e:
        logger.error(f"[GetPlayerStats] Error: {e}")
        return jsonify({"result": 1})


# --- КОНФИГУРАЦИЯ РАНГА (Сезон 1 для 1.22.1) ---

@app.route('/GetCurOrRecentRankingConfig', methods=['POST'])
def get_ranking_config():
    try:
        now = int(time.time())
        # Используем Сезон 1, чтобы иконки точно прогрузились
        season_id = 1 

        season_info = {
            "season_id": season_id,
            "season_type": 1,
            "begin_time": 0,            # Вечный сезон с 1970 года
            "end_time": 4102444800,     # До 2100 года
            "history_begin_time": 0,
            "history_end_time": 4102444800
        }

        return jsonify({
            "result": 0,
            "season_info": season_info,
            "awards": []
        })

    except Exception as e:
        logger.error(f"[GetCurOrRecentRankingConfig] Error: {e}")
        return jsonify({"result": 0})


# --- РАНГ ИГРОКА ---

@app.route('/GetPlayerRankingInfo', methods=['POST'])
def get_player_ranking_info():
    try:
        user = get_user_from_request()

        # Дефолтные значения, если в базе пусто
        rank = 19
        points = 10000

        if user:
             rank = int(user.get('rank', 19))
             points = int(user.get('ranking_points', 10000))

        return jsonify({
            "result": 0,
            "rank": rank,
            "ranking_points": points,
            "last_modified_time": int(time.time()),
            "max_rank": rank
        })
    except Exception as e:
        logger.error(f"[GetPlayerRankingInfo] Error: {e}")
        return jsonify({"result": 1})



@app.route('/GetActivityDesc', methods=['POST'])
def get_activity_desc():
    try:
        now = int(time.time())
        
        # Создаем одно тестовое событие
        dummy_event = {
            "activity_id": 1,
            "group_id": 1,
            "activity_type": 1,       # 1 обычно Login Event или Простой текст
            "sort_id": 1,
            "is_process_show": 1,
            "act_tag": 0,
            "gos_pos": 0,
            
            # Время должно быть строкой (string) по твоей структуре C#
            "start_time": str(now - 86400),    # Началось вчера
            "end_time": str(now + 31536000),   # Закончится через год
            "show_time": str(now - 86400),
            
            "circle_type": 0,
            
            # Условия (PreConditionType) - ставим 0 (без условий)
            "pre_cdt_type1": 0, "pre_cdt_value1": 0,
            "pre_cdt_type2": 0, "pre_cdt_value2": 0,
            "pre_cdt_type3": 0, "pre_cdt_value3": 0,
            "pre_cdt_type4": 0, "pre_cdt_value4": 0,
            "pre_cdt_type5": 0, "pre_cdt_value5": 0,
            
            "cdt_type": 0,
            "cdt_value": 0,
            
            # Награды (пустой список пока)
            "awards": [],
            
            # Предмет для обмена (если это событие обмена)
            "exchange_item": {"id": 0, "cnt": 0}
        }

        return jsonify({
            "activity_descs": [dummy_event] 
        })
        
    except Exception as e:
        logger.error(f"[GetActivityDesc] Error: {e}")
        return jsonify({"activity_descs": []})


@app.route('/GetAttendanceList', methods=['POST'])
def get_attendance_list():
    try:
        end_time = int(time.time()) + 31536000 # Год длительности
        
        # --- ФОРМИРУЕМ НАГРАДУ (ДЕНЬ 1) ---
        # Структура основана на твоем классе AttendanceItem
        day_1 = {
            "id": 1,            # День 1
            "signed": 1,        # 0 = Не подписано (Доступно к сбору)
            "awards": [         # Список наград (List<AwardDesc>)
                {
                    "item_id": 1,    # Золото
                    "cnt": 10000,      # 100 монет
                    "is_show": 1     # Показывать (на всякий случай)
                }
            ]
        }

        return jsonify({
            "attendance": [day_1], # Массив дней
            "end_time": end_time,
            "url": "",             
            "loc_key": ""
        })
        
    except Exception as e:
        logger.error(f"[GetAttendanceList] Error: {e}")
        return jsonify({"attendance": [], "end_time": 0, "url": "", "loc_key": ""})


@app.route('/AttendanceSignin', methods=['POST'])
def attendance_signin():
    # Клиент отправляет этот запрос, когда жмет "Забрать"
    try:
        user = get_user_from_request()
        
        # В идеале здесь нужно добавить золото в базу данных
        # user['gold'] += 100 
        # save_user(user)

        # Возвращаем успех
        return jsonify({
            "result": 0,
            
            # Клиент может ожидать обновленный список наград
            # Возвращаем награду, которую только что дали
            "awards": [
                 {
                    "item_id": 1,
                    "cnt": 100,
                    "is_show": 1
                }
            ]
        })
    except Exception as e:
        logger.error(f"[AttendanceSignin] Error: {e}")
        return jsonify({"result": 1}) # 1 = Ошибка


@app.route('/GetMailList', methods=['POST'])
def get_mail_list():
    try:
        current_time = int(time.time())
        
        mail_item = {
            "mail_id": 10006,
            "type": 0,             # 0 = Обычное письмо
            
            "title": "ПРИВЕТ!",
            "content": "СПАСИБО ЗА ВХОД В ИГРУ!",
            
            "receive_time": current_time,
            "status": 0,           # 0 = Не прочитано
            "source": 1,           # 1 = ADMIN (Важно, чтобы работало вложение)
            "action_type": 1,      # 0 = ATTACHMENT (Есть вложение)

            # --- SENDER INFO (По твоей структуре) ---
            "sender_info": {
                "sender_id": 0,           # 0 = Система
                "sender_nick": "MELISOV",   # Имя отправителя
                
                # Остальные поля можно оставить пустыми или 0
                "clan_id": 0,
                "clan_name": "",
                "clan_captain_id": 0,
                "clan_captain_nick": "",
                "season_id": 0,
                "season_rank": 0,
                "ep_unlock_id": 0,
                "ep_challenge_id": 0,
                "gift_message": ""
            },
            
            # --- ATTACHMENT (По твоей структуре) ---
            "attachment": {
                # В C# это поле называется "rewards" типа AwardData
                "rewards": {
                    # Внутри AwardData обычно лежит список наград.
                    # Чаще всего он называется "awards" или "items".
                    "awards": [
                        {
                            "item_id":2,    # 2 = Gems (Алмазы)
                            "cnt": 1000    # Количество
                        }
                    ]
                }
            }
        }

        return jsonify({
            "mails": [mail_item]
        })

    except Exception as e:
        logger.error(f"[GetMailList] Error: {e}")
        return jsonify({"mails": []})


@app.route('/ReadMail', methods=['POST'])
def read_mail():
    # Клиент сообщает, что открыл письмо
    return jsonify({"result": 0})


@app.route('/GetMailAttachment', methods=['POST'])
def get_mail_attachment():
    try:
        # Тут мы говорим клиенту "ОК, награда выдана"
        # Реальное начисление гемов надо делать в БД
        return jsonify({
            "result": 0,
            "awards": [
                {"item_id": 2, "cnt": 10000}
            ]
        })
    except Exception as e:
        return jsonify({"result": 1})



import random

@app.route('/CreateClan', methods=['POST'])
def create_clan():
    try:
        data = request.get_json(force=True, silent=True)
        print(f"[DEBUG] CreateClan Data: {data}")

        conn = get_db_connection()
        # Чтобы обращаться к колонкам по имени
        conn.row_factory = sqlite3.Row 

        # 1. Берем первого игрока из базы (самый надежный способ для тестов)
        user_row = conn.execute('SELECT * FROM users LIMIT 1').fetchone()

        if not user_row:
            conn.close()
            print("[CreateClan] ОШИБКА: База данных пуста!")
            return jsonify({"result": 1})

        # 2. Превращаем строку БД в словарь
        user_data = dict(user_row)

        # --- БЕЗОПАСНОЕ ПОЛУЧЕНИЕ ДАННЫХ (ЧТОБЫ НЕ БЫЛО ОШИБОК) ---

        # Ищем ID: сначала account_id, если нет - то id, иначе 0
        user_id = user_data.get('account_id') or user_data.get('id') or 0

        # Ищем ИМЯ: сначала nickname, если нет - name, иначе "Player"
        user_name = user_data.get('nickname') or user_data.get('name') or "Player"

        # Уровень и аватарка
        user_level = user_data.get('level', 1)
        user_avatar = user_data.get('avatar_id', 101000006)

        print(f"[DEBUG] Создаем клан для: {user_name} (ID: {user_id})")
        # -----------------------------------------------------------

        # Данные от клиента
        clan_name = data.get('clan_name', f"Clan {user_name}")
        clan_id = str(random.randint(100000, 999999))
        logo = data.get('clan_logo', 1)
        slogan = data.get('slogan', 'Welcome')

        # 3. Структура клана
        new_clan = {
            "clan_id": int(clan_id),
            "clan_name": clan_name,
            "create_at": int(time.time()),
            "captain_id": user_id,
            "clan_level": 1,
            "capacity": 20,
            "member_num": 1,
            "entry_level": 1,
            "entry_type": 0,
            "clan_logo": logo,
            "announcement": "",
            "slogan": slogan,
            "region": "RU",

            # Добавляем тебя в участники
            "members": [{
                "id": user_id,
                "name": user_name,
                "role": 2,          # 2 = Капитан
                "trophies": 0,
                "level": user_level,
                "status": 1,
                "avatar_id": user_avatar
            }]
        }

        # 4. Сохраняем в файл JSON
        clans = load_clans()
        clans[clan_id] = new_clan
        save_clans(clans)

        # 5. Обновляем БД (записываем ID клана пользователю)
        # Проверяем, есть ли колонка account_id, чтобы не упасть при update
        if 'account_id' in user_data:
            conn.execute('UPDATE users SET clan_id = ? WHERE account_id = ?', (clan_id, user_id))
        else:
            conn.execute('UPDATE users SET clan_id = ? WHERE id = ?', (clan_id, user_id))

        conn.commit()
        conn.close()

        print(f"[INFO] Клан {clan_name} ({clan_id}) успешно создан!")
        return jsonify({"result": 0}) 

    except Exception as e:
        print(f"[CreateClan] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc() # Покажет подробности ошибки в консоли
        return jsonify({"result": 1})



@app.route('/GetClanMembers', methods=['POST'])
def get_clan_members():
    try:
        data = request.get_json(force=True, silent=True)
        # 1. Ищем игрока в базе, чтобы узнать его ID клана
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row # Чтобы обращаться по именам колонок

        # Пытаемся найти по токену, если нет - берем первого (как в CreateClan)
        token = data.get('token')
        user = conn.execute('SELECT * FROM users WHERE token = ?', (token,)).fetchone()

        if not user:
             # Аварийный вариант (для тестов)
             user = conn.execute('SELECT * FROM users LIMIT 1').fetchone()

        if not user:
            conn.close()
            return jsonify({"members": []}) # Нет юзера - нет списка

        user_data = dict(user)
        conn.close()

        # 2. Получаем ID клана из базы данных
        clan_id = user_data.get('clan_id', 0)

        if not clan_id or clan_id == 0:
            print(f"[GetClanMembers] У пользователя {user_data.get('nickname')} нет клана (clan_id=0)")
            return jsonify({"members": []})

        # 3. Загружаем файл с кланами
        clans = load_clans()

        # Ищем клан по ID (конвертируем в строку, так как в JSON ключи - строки)
        my_clan = clans.get(str(clan_id))

        if not my_clan:
            print(f"[GetClanMembers] Клан {clan_id} записан в базе, но не найден в JSON файле!")
            return jsonify({"members": []})

        # 4. Отправляем список участников
        print(f"[GetClanMembers] Отправляем состав клана {my_clan['clan_name']} игроку")
        return jsonify({
            "members": my_clan['members']
        })

    except Exception as e:
        print(f"[GetClanMembers] Error: {e}")
        return jsonify({"members": []})
        
        
@app.route('/GetRandomClanList', methods=['POST'])
def get_random_clan_list():
    try:
        # data = request.get_json(force=True, silent=True) # Параметры не особо важны

        clans = load_clans() # Загружаем словарь из файла
        
        clan_list = []
        
        # Перебираем все кланы и добавляем в список
        for clan_id, clan_data in clans.items():
            # На всякий случай проверяем, не удален ли клан (если есть такая логика)
            # и добавляем только существующие
            if clan_data: 
                clan_list.append(clan_data)

        # Перемешиваем, чтобы список был "рандомным" (опционально)
        random.shuffle(clan_list)

        # Отправляем список (максимум 50 штук)
        return jsonify({
            "clan_list": clan_list[:50]
        })

    except Exception as e:
        print(f"[GetRandomClanList] Error: {e}")
        # В случае ошибки возвращаем пустой список, чтобы игра не зависла
        return jsonify({"clan_list": []})



@app.route('/GetClanInfoByClanID', methods=['POST'])
def get_clan_info_by_id():
    try:
        # force=True обязательно
        data = request.get_json(force=True, silent=True)
        
        if not data:
            return jsonify({"infos": []})

        # Получаем ID, который просит игра
        target_clan_id = str(data.get('clan_id'))
        
        clans = load_clans()
        
        if target_clan_id in clans:
            # Возвращаем список с одним кланом
            return jsonify({
                "infos": [clans[target_clan_id]]
            })
        else:
            return jsonify({"infos": []})

    except Exception as e:
        print(f"[GetClanInfoByClanID] Error: {e}")
        return jsonify({"infos": []})



@app.route('/GetEPInfo', methods=['POST'])
def get_ep_info():
    try:
        # Получаем данные пользователя из базы данных (game.db)
        user = get_user_from_request()

        if not user:
            print("[GetEPInfo] User not found or invalid token")
            return jsonify({})

        # Отладка: выводим весь полученный пользовательский словарь
        print(f"[GetEPInfo] User data: {user}")

        # Проверяем и выводим badge_cnt
        badge_count = user.get('badge_cnt', 0)
        print(f"[GetEPInfo] badge_cnt из базы: {badge_count}")

        # Обеспечиваем, что badge_count — это число
        badges = int(badge_count) if badge_count is not None else 0

        current_time = int(time.time())
        end_time = current_time + (30 * 24 * 60 * 60)  # Сезон кончится через 30 дней

        # --- Формируем ответ ---
        response = {
            "owned_pass": bool(user.get('has_elite_pass', False)),
            "owned_fp_challenge": True,

            "ep_event_id": 1,

            "start_time": current_time - 86400,
            "end_time": end_time,

            "ep_badge": int(user.get('badge_id', 1001000002)),
            "badge_cnt": badges,

            "gold_limit_improved": badges,
            "fp_challenge_item": badges,
            "purchase_badge_count_today": badges,
            "week": 1,
            "daily_reset_time": end_time,

            "rewards": [],
            "challenges": []
        }

        print(f"[GetEPInfo] User: {user.get('nickname')} | ElitePass: {response['owned_pass']} | Badges: {badges}")
        return jsonify(response)

    except Exception as e:
        print(f"[GetEPInfo] Error: {e}")
        return jsonify({})



@app.route('/GetAllSwitchs', methods=['POST'])
def get_all_switchs():
    try:
        # Игра может присылать регион, но нам это пока не важно
        # data = request.get_json(force=True, silent=True)

        print("[GetAllSwitchs] Запрос настроек (свитчей). Отправляем стандартные.")

        # Возвращаем пустой список. 
        # В C# это поле называется "switchs" (с опечаткой разработчиков игры, это нормально)
        return jsonify({
            "switchs": [] 
        })

    except Exception as e:
        print(f"[GetAllSwitchs] Error: {e}")
        # В случае ошибки тоже шлем пустой список, чтобы игра не зависла
        return jsonify({"switchs": []})




# 2. Открытие сундука (на случай, если игра попытается что-то открыть)
@app.route('/OpenTreasureBox', methods=['POST'])
def open_treasure_box():
    try:
        data = request.get_json(force=True, silent=True)
        t_id = data.get('treasure_id', 0)
        print(f"[OpenTreasureBox] Попытка открыть сундук ID: {t_id}")

        # Возвращаем заглушку, что наград нет, сундуков осталось 0
        return jsonify({
            "awards": {
                # Сюда можно добавить награды, если знать структуру AwardData
                # Пока отправляем пустоту, чтобы не крашнулось
            },
            "left_box_num": 0,
            "exchangedAwards": []
        })

    except Exception as e:
        print(f"[OpenTreasureBox] Error: {e}")
        return jsonify({})

@app.route('/GetAdvert', methods=['POST'])
def get_advert():
    try:
        print("[GetAdvert] Отправляем баннер...")

        # Текущее время
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        # Будущее время
        future = "2030-01-01 00:00:00"

        response = {
            "advert_items": [
                {
                    "id": 1,
                    "type": 2,              # 1 = Pop-up (Всплывающее), 2 = Billboard
                    "sort_id": 1,
                    "language": "ru",      # "all" - для всех языков
                    "advertisment_url": "https://i.pinimg.com/originals/c5/a6/a7/c5a6a7123f26730ee4e375ea70d3c4e2.jpg",
                    "ad_start_time": "2020-01-01 00:00:00",
                    "ad_end_time": future,
                    "go_pos": 0,            # 0 = просто картинка
                    "sub_type": 0,
                    "sub_go_pos": "",
                    "external_for_official_website": False
                }
            ]
        }
        return jsonify(response)
    except Exception as e:
        print(f"[GetAdvert] Error: {e}")
        return jsonify({"advert_items": []})

    except Exception as e:
        print(f"[GetAdvert] Error: {e}")
        return jsonify({"advert_items": []})


@app.route('/EPPurchaseBadge', methods=['POST'])
def ep_purchase_badge():
    try:
        user = get_user_from_request()
        
        if not user:
            print("[EPPurchaseBadge] User not found")
            return jsonify({})

        data = request.get_json(force=True, silent=True) or {}
        count = int(data.get('count', 0))       # Количество значков

        # --- НАСТРОЙКА ЦЕНЫ ---
        PRICE_PER_BADGE = 25  # Цена за 1 значок (обычно 25 алмазов)

        if count > 0:
            total_cost = count * PRICE_PER_BADGE
            current_gems = int(user.get('gems', 0))
            
            print(f"[EPPurchaseBadge] Игрок хочет купить {count} значков. Цена: {total_cost}. Баланс: {current_gems}")

            # 1. Проверяем, хватает ли денег
            if current_gems >= total_cost:
                # 2. Списываем алмазы
                new_gems = current_gems - total_cost
                user['gems'] = new_gems
                
                # 3. Добавляем значки
                current_badges = int(user.get('badge_cnt', 0))
                new_badges = current_badges + count
                user['badge_cnt'] = new_badges

                # 4. Сохраняем в БД
                save_user_to_db(user)

                print(f"[EPPurchaseBadge] УСПЕХ! Списано {total_cost} алмазов. Новых значков: {new_badges}")
                
                # Возвращаем результат 0 (успех) и новый баланс, чтобы клиент обновился
                return jsonify({
                    "result": 0,
                    "new_gems": new_gems,
                    "new_badges": new_badges
                })
            else:
                print("[EPPurchaseBadge] ОШИБКА: Недостаточно алмазов!")
                # Возвращаем ошибку (обычно 1 или просто игнор)
                return jsonify({"result": 1})

        return jsonify({"result": 0})

    except Exception as e:
        print(f"[EPPurchaseBadge] Error: {e}")
        return jsonify({})





@app.route('/GetNewPlayerRewardsList', methods=['POST'])
def get_new_player_rewards_list():
    try:
        # data = request.get_json(force=True, silent=True) # Если нужен account_id

        print("[GetNewPlayerRewardsList] Запрос наград новичка. Отправляем пустой список.")

        # Возвращаем пустой список наград.
        # Это скажет игре, что наград нет, и окно просто не откроется или будет пустым.
        return jsonify({
            # Пример (пока не используй, если не уверен в ID предметов):
"rewards": [
    {"day": 1, "item_id": 101, "amount": 100, "status": 1}, # 1 день: 100 золота
    {"day": 2, "item_id": 102, "amount": 10, "status": 0},  # 2 день: 10 алмазов
    # и так далее...
]

        })

    except Exception as e:
        print(f"[GetNewPlayerRewardsList] Error: {e}")
        return jsonify({"rewards": []})



@app.route('/GetVeteranRewardList', methods=['POST'])
def get_veteran_reward_list():
    try:
        # data = request.get_json(force=True, silent=True) # Можно получить account_id

        print("[GetVeteranRewardList] Проверка статуса ветерана. Отправляем: False")

        return jsonify({
            "is_veteran": False, # Говорим игре: "Это не вернувшийся игрок"
            "rewards": []        # Список наград пустой
        })

    except Exception as e:
        print(f"[GetVeteranRewardList] Error: {e}")
        return jsonify({"is_veteran": False, "rewards": []})

@app.route('/GetCollectionHide', methods=['POST'])
def get_collection_hide():
    try:
        # Обычно здесь возвращают список ID предметов, которые нужно скрыть из коллекции
        # Если мы хотим, чтобы все было видно - возвращаем пустой список
        print("[GetCollectionHide] Запрос скрытых предметов")
        return jsonify({
            "item_ids": [] 
        })
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"item_ids": []})

@app.route('/GetBackpack', methods=['POST'])
def get_backpack():
    try:
        user = get_user_from_request()
        if not user:
            return jsonify({"wallet": {"gold": 0, "diamond": 0}, "items": [], "selected_items": {}})

        print(f"[GetBackpack] Генерация инвентаря для {user.get('nickname')}...")

        user_inventory = user.get('inventory', [])
        items_list = []

        for item in user_inventory:
            i_id = int(item.get('iID', 0))
            equip_status = int(item.get('equip', 0))

            client_item = {
                "itemId": i_id,
                "amount": 1,        # Количество
                "count": 1,         # Дублируем для совместимости
                "equip": equip_status,
                "expire": -1,       # <--- МЕНЯЕМ НА -1 (Означает "Навсегда")
                "is_stack": 0,
                "valid": True       # Иногда нужно это поле
            }
            items_list.append(client_item)

        response = {
            "wallet": {
                "gold": int(user.get('coins', 99999)),
                "diamond": int(user.get('gems', 99999))
            },
            "items": items_list,
            "selected_items": {}
        }
        
        print(f"[GetBackpack] Отправлено {len(items_list)} предметов (Expire: -1).")
        return jsonify(response)

    except Exception as e:
        print(f"[GetBackpack] Error: {e}")
        return jsonify({"items": []})




@app.route('/SelectProfile', methods=['POST'])
def select_profile():
    try:
        # 1. Находим игрока
        user = get_user_from_request()
        if not user:
            print("[SelectProfile] User not found")
            return jsonify({})

        # 2. Читаем, какого персонажа выбрал игрок
        data = request.get_json(force=True, silent=True)
        avatar_id = int(data.get('avatar_id', 0))

        if avatar_id > 0:
            print(f"[SelectProfile] Игрок {user['nickname']} меняет персонажа на ID: {avatar_id}")

            # --- ОБНОВЛЕНИЕ БАЗЫ ---
            user['avatar_id'] = avatar_id
            
            # Сохраняем изменения в файл game.db
            save_user_to_db(user)

            # --- ФОРМИРОВАНИЕ ОТВЕТА ---
            # Клиент ждет объект "profile" (AvatarProfile)
            # Мы заполняем его данными из базы (уровень, опыт) и новым ID
            
            response = {
                "profile": {
                    "avatar_id": avatar_id,
                    "role_id": avatar_id,       # Часто дублируется
                    "sex": 0,                   # 0 - муж, 1 - жен (можно усложнить логику, если есть база ID)
                    "level": int(user.get('level', 1)),
                    "exp": int(user.get('exp', 0)),
                    "hp": 200,                  # Дефолтное HP
                    "max_hp": 200,
                    # Можно добавить скиллы, если они хранятся в базе
                    "equip_skill": []           
                }
            }
            
            return jsonify(response)
        
        else:
            print("[SelectProfile] Пришел неверный ID персонажа")
            return jsonify({})

    except Exception as e:
        print(f"[SelectProfile] Error: {e}")
        return jsonify({})


@app.route('/ChangeClothes', methods=['POST'])
def change_clothes():
    try:
        # 1. Получаем пользователя
        user = get_user_from_request()
        if not user:
            print("[ChangeClothes] User not found")
            return jsonify({})

        # 2. Получаем данные от клиента
        data = request.get_json(force=True, silent=True)
        
        avatar_id = int(data.get('avatar_id', 0))
        clothes_list = data.get('clothes', [])  # Это список ID предметов [101, 202, 303...]
        skin_color = int(data.get('skin_color', 0))

        print(f"[ChangeClothes] Игрок {user['nickname']} надевает: {clothes_list}")

        # 3. Сохраняем в базу данных
        # Мы сохраняем список надетой одежды в поле 'equipped_items' (или 'clothes')
        user['avatar_id'] = avatar_id
        user['skin_color'] = skin_color
        user['equipped_items'] = clothes_list 
        
        # ВАЖНО: Если у тебя инвентарь хранит статус equip внутри списка предметов,
        # тут можно добавить цикл для обновления статуса equip=1 для этих ID.
        # Но для простого сервера достаточно сохранить список отдельно.

        save_user_to_db(user)

        # 4. Формируем ответ (HTTP_ChangeClothesRes)
        # Клиент ждет объект "profile" (AvatarProfile)
        response = {
            "profile": {
                "avatar_id": avatar_id,
                "role_id": avatar_id,
                "sex": int(user.get('sex', 0)), # 0 - муж, 1 - жен
                "level": int(user.get('level', 1)),
                "exp": int(user.get('exp', 0)),
                "hp": 200,
                "max_hp": 200,
                "skin_color": skin_color,
                # Если игра требует вернуть список одежды в профиле:
                # "clothes": clothes_list 
            }
        }

        return jsonify(response)

    except Exception as e:
        print(f"[ChangeClothes] Error: {e}")
        return jsonify({})


@app.route('/GetGachaDesc', methods=['POST'])
def get_gacha_desc():
    try:
        # Список призов для Gold Royale (ID 1001)
        gold_items = [
            {
                "item_id": 11001,       # Маска черепа (пример)
                "item_num": 1,          # Количество
                "item_type": 1,         # 1 - Экипировка, 2 - Расходник
                "is_show": True,        # Показывать ли в списке
                "reward_level": 1,      # 1 - Золотое свечение, 0 - Обычное
                "repeated_item_id": 0,  # Что дать, если уже есть (0 - ничего)
                "repeated_item_num": 0
            },
            {
                "item_id": 11101,       # Футболка
                "item_num": 1,
                "item_type": 1,
                "is_show": True,
                "reward_level": 0,
                "repeated_item_id": 0,
                "repeated_item_num": 0
            },
            {
                "item_id": 12006,       # Костер (Bonfire)
                "item_num": 1,
                "item_type": 2,         # Тип 2 (Item)
                "is_show": True,
                "reward_level": 0,
                "repeated_item_id": 0,
                "repeated_item_num": 0
            }
        ]

        response = {
            "gacha_desc_list": [
                {
                    "chest_id": 1001,
                    "chest_type": 1,
                    "item_list": gold_items,
                    "extra_rewards": []
                },
                # Можно добавить Diamond Royale (1002) по аналогии
            ]
        }
        return jsonify(response)
    except Exception as e:
        print(f"[GetGachaDesc] Error: {e}")
        return jsonify({})










@app.route('/GetGachaInfo', methods=['POST'])
def get_gacha_info():
    try:
        user = get_user_from_request()

        # 0 = Бесплатно прямо сейчас (Free Spin Available)
        # Если поставить time.time() + 3600, будет таймер 1 час
        free_spin_time = 0 

        response = {
            "gacha_info_list": [
                # Настройки для Gold Royale
                {
                    "chest_id": 1001,
                    "lottery_count_weekly": 0,    # Сколько раз крутил на этой неделе
                    "exchanged_reward_list": [],  # Награды за кол-во прокрутов
                    "next_free_time": free_spin_time,
                    "not_got_num": 0,             # "Удача" (Luck)
                    "limit_purchase_count_one": 9999,
                    "limit_purchase_count_ten": 9999,
                    "first_draw_reward_num": 0
                },
                # Настройки для Diamond Royale
                {
                    "chest_id": 1002,
                    "lottery_count_weekly": 0,
                    "exchanged_reward_list": [],
                    "next_free_time": free_spin_time, # Тоже бесплатно
                    "not_got_num": 90,            # Типа высокая удача
                    "limit_purchase_count_one": 9999,
                    "limit_purchase_count_ten": 9999,
                    "first_draw_reward_num": 0
                }
            ]
        }
        return jsonify(response)

    except Exception as e:
        print(f"[GetGachaInfo] Error: {e}")
        return jsonify({})


@app.route('/PurchaseGacha', methods=['POST'])
def purchase_gacha():
    try:
        user = get_user_from_request()
        data = request.get_json(force=True, silent=True)

        chest_id = data.get('chest_id')

        # Определяем, что выпало (для теста всегда выпадает ID 11001)
        # В реальности тут нужен random.choice из списка
        prize_id = 11001 
        prize_type = 1    # 1 - Equip

        # Структура выпавшего предмета (ExchangedAward)
        won_item = {
            "award_type": prize_type,
            "id": prize_id,
            "amount": 1
        }

        print(f"Игрок {user.get('nickname')} крутит рулетку {chest_id} и получает {prize_id}")

        # Тут можно списать золото/алмазы у user, если нужно

        response = {
            "lottery_goods": [won_item],    # Что выиграл
            "reward_goods": [],             # Бонусы (если есть)
            "extra_one_goods": [],          # Доп. бонусы
            "lottery_count_weekly": 1,      # Обновляем счетчик
            "next_free_time": 0             # Таймер бесплатного спина
        }

        return jsonify(response)

    except Exception as e:
        print(f"[PurchaseGacha] Error: {e}")
        return jsonify({})

@app.route('/ExchangeGachaExtraReward', methods=['POST'])
def exchange_extra_reward():
    # Просто возвращаем пустой успех
    return jsonify({
        "award_data": {},
        "exchanged_reward_list": []
    })

#########################################################################################################


@app.route('/GetStore', methods=['POST'])
def get_store():
    try:
        now_time = "2020-01-01 00:00:00"
        end_time = "2030-01-01 00:00:00"

        items = [
            # --- ТОВАР 1: Вкладка NEW ---
            {
                "store_id": 10001,       # Большой ID для уникальности
                "sort_id": 1,
                "item_id": 11101,        # Белая футболка (Basic T-Shirt)
                "name": "White Shirt",
                "desc": "Basic",
                "coins_price": 100,      # Цена 100 золота
                "gems_price": 0,
                "tag_type": 1,           # 1 = NEW
                "tag_value": 0,
                "limited_purchase_times": 100, # ВАЖНО: Большой лимит
                "purchase_times": 0,
                "is_new": True,
                "added_time": now_time,
                "expire_time": end_time
            },
            # --- ТОВАР 2: Вкладка FASHION (Обычно store_id определяет вкладку) ---
            {
                "store_id": 20001,
                "sort_id": 2,
                "item_id": 11201,        # Штаны (Basic Pants)
                "name": "Jeans",
                "desc": "Basic",
                "coins_price": 0,
                "gems_price": 50,        # Цена 50 алмазов
                "tag_type": 2,           # 2 = HOT
                "tag_value": 0,
                "limited_purchase_times": 100,
                "purchase_times": 0,
                "is_new": False,
                "added_time": now_time,
                "expire_time": end_time
            },
            # --- ТОВАР 3: Вкладка ITEMS (Расходники) ---
            {
                "store_id": 30001,
                "sort_id": 3,
                "item_id": 12006,        # Костер (Bonfire)
                "name": "Bonfire",
                "desc": "Survival",
                "coins_price": 50,
                "gems_price": 0,
                "tag_type": 0,
                "tag_value": 0,
                "limited_purchase_times": 100,
                "purchase_times": 0,
                "is_new": False,
                "added_time": now_time,
                "expire_time": end_time
            }
        ]

        return jsonify({"store_items": items})

    except Exception as e:
        print(f"[GetStore] Error: {e}")
        return jsonify({})


@app.route('/GetGiftStore', methods=['POST'])
def get_gift_store():
    try:
        # Описываем категорию подарков
        gift_categories = [
            {
                "store_id": 1,               # ID категории подарков
                "open_time": "2020-01-01 00:00:00",
                "close_time": "2030-01-01 00:00:00",
                "is_time_show": False,
                "giver_level": 5,            # Отправитель должен быть 5 уровня
                "receiver_level": 5,         # Получатель должен быть 5 уровня
                "gift_time_limited": 0,
                "gift_num_limited": 5        # Максимум 5 подарков в день
            }
        ]

        # Обрати внимание: в некоторых версиях поле называется store_items, в некоторых store_list
        # Твой класс GetGiftStoreRes не показан полностью, но обычно это store_items
        return jsonify({"store_items": gift_categories}) 
    except Exception as e:
        print(f"[GetGiftStore] Error: {e}")
        return jsonify({})

@app.route('/GetGiftStoreDetails', methods=['POST'])
def get_gift_store_details():
    try:
        # Товары, доступные для дарения
        gift_items = [
            {
                "store_id": 1,           # Ссылка на ID из GetGiftStore
                "commodity_id": 1001,    # Уникальный ID товара
                "sort_id": 1,
                "item_id": 11001,        # ID предмета (Маска)
                "coins_price": 0,
                "gems_price": 100,       # Подарки обычно только за алмазы
                "tag_type": 0,
                "tag_value": 0,
                "return_type": 1,        # Если у друга уже есть, вернуть золото? (1=Equip)
                "return_id": 0,
                "return_num": 0,
                "added_time": "2020-01-01 00:00:00",
                "expire_time": "2030-01-01 00:00:00"
            }
        ]

        return jsonify({"store_items": gift_items})
    except Exception as e:
        print(f"[GetGiftStoreDetails] Error: {e}")
        return jsonify({})
        
        
@app.route('/GetExchangeStore', methods=['POST'])
def get_exchange_store():
    try:
        # 1. Описание магазина обмена
        desc = {
            "exchange_store_desc": {
                "store_id": 1,
                "name": "Token Exchange",
                "open_time": "2020-01-01 00:00:00",
                "close_time": "2030-01-01 00:00:00"
            }
        }

        # 2. Список товаров
        items = [
            {
                "store_id": 1,
                "commodity_id": 2001,
                "sort_id": 1,
                "name": "Free Pants",
                "item_id": 11201,       # Штаны
                "currency_id": 8001,    # ID валюты (например, FF Token)
                "currency_name": "FF Token",
                "currency_price": 50,   # Цена: 50 токенов
                "tag_type": 0,
                "tag_value": 0,
                "limited_purchase_times": 0,
                "purchase_times": 0,
                "added_time": "2020-01-01 00:00:00",
                "expire_time": "2030-01-01 00:00:00"
            }
        ]

        return jsonify({
            "exchange_store_desc": desc["exchange_store_desc"],
            "exchange_store_items": items
        })
    except Exception as e:
        print(f"[GetExchangeStore] Error: {e}")
        return jsonify({})
        
        
        
@app.route('/ChooseLoadout', methods=['POST'])
def choose_loadout():
    try:
        user = get_user_from_request()
        # Клиент отправляет список ID (loadouts), которые выбрал игрок
        data = request.get_json(force=True, silent=True)

        loadouts = data.get('loadouts', [])
        print(f"[ChooseLoadout] Игрок {user.get('nickname')} выбрал предметы: {loadouts}")

        # Сервер должен просто подтвердить выбор.
        # Обычно ответ пустой или success: true, так как класс ответа (Res) не требуется.
        return jsonify({"result": 0})

    except Exception as e:
        print(f"[ChooseLoadout] Error: {e}")
        return jsonify({})
        
        
        
@app.route('/GetCards', methods=['POST'])
def get_cards():
    try:
        # data = request.get_json(force=True, silent=True)
        # account_id = data.get('account_id')

        print("[GetCards] Запрос состояния карт (Flip Card Event)")

        response = {
            "enable_flip": True,          # Включить возможность переворачивать?
            "win_award": False,           # Выиграл ли уже?
            "card_price": [],             # Список цен (можно оставить пустым для теста)
            "awards": [],                 # Список уже полученных наград
            "flip_count_today": 0,        # Сколько раз переворачивал сегодня
            "flip_count_max": 5           # Максимум попыток
        }
        
        return jsonify(response)

    except Exception as e:
        print(f"[GetCards] Error: {e}")
        return jsonify({})
        
        
        
        
@app.route('/GetFreePlayCards', methods=['POST'])
def get_free_play_cards():
    try:
        # data = request.get_json(force=True, silent=True)
        
        print("[GetFreePlayCards] Запрос пробных карт")

        # Отправляем пустой список. 
        # Если захочешь дать игроку временного персонажа, это делается здесь.
        response = {
            "play_cards": [] 
        }

        return jsonify(response)

    except Exception as e:
        print(f"[GetFreePlayCards] Error: {e}")
        return jsonify({})
       
        
        
@app.route('/GetBundle', methods=['POST'])
def get_bundle():
    try:
        print("[GetBundle] Запрос списка наборов")

        # Структура BundleShow
        bundles = [
            {
                "id": 1,            # ID категории наборов
                "bundles": []       # Список содержимого (BundleShowData). Оставляем пустым, чтобы не гадать структуру.
            }
        ]

        # Возвращаем объект с полем bundle_show
        return jsonify({"bundle_show": bundles})

    except Exception as e:
        print(f"[GetBundle] Error: {e}")
        return jsonify({})
       
        
        
        
@app.route('/OpenBundle', methods=['POST'])
def open_bundle():
    try:
        user = get_user_from_request()
        data = request.get_json(force=True, silent=True)
        
        item_id = data.get('item_id') # ID набора, который открывают
        print(f"[OpenBundle] Игрок {user.get('nickname')} пытается открыть набор {item_id}")

        # Формируем ответ об успехе, но без наград (пока что)
        response = {
            "data": {},                 # ExchangeChangeData (обычно изменения валюты)
            "transfer_to_items": []     # AwardDesc[] (список полученных предметов)
        }

        return jsonify(response)

    except Exception as e:
        print(f"[OpenBundle] Error: {e}")
        return jsonify({})
        
        
@app.route('/GetTreasureBox', methods=['POST'])
def get_treasure_box():
    try:
        # data = request.get_json(force=True, silent=True)
        print("[GetTreasureBox] Запрос сундуков (Elite Pass / Daily)")

        # Формируем ответ. 
        # В версии 1.22.x структура обычно содержит "modules" или "treasures".
        # Отправляем пустые списки, чтобы игра поняла, что доступных сундуков пока нет.
        response = {
            "modules": [],      # Основной список модулей сундуков
            "treasures": []     # Список конкретных наград/сокровищ
        }
        
        return jsonify(response)

    except Exception as e:
        print(f"[GetTreasureBox] Error: {e}")
        return jsonify({})
        
        
 







@app.route('/GetBroadcastList', methods=['POST'])
def get_broadcast_list():
    try:
        print("[GetBroadcastList] Запрос списка объявлений (Бегущая строка)")

        # Создаем фиктивное сообщение для теста
        # Если хочешь пустую строку - просто оставь список пустым []
        messages = [
            {
                "nickname": "System",       # Имя игрока/системы
                "navigation_type": 0,       # Тип перехода при клике (0 = ничего)
                "source": "Server",         # Источник (например, "Gacha")
                "item_id": 11101,           # ID предмета (например, наша футболка)
                "time_stamp": int(time.time()), # Время
                "source_id": 0              # ID источника
            }
        ]

        response = {
            "broadcast_messages": messages,
            "silence_show_switch": True     # Показывать ли переключатель "Не беспокоить"
        }

        return jsonify(response)

    except Exception as e:
        print(f"[GetBroadcastList] Error: {e}")
        return jsonify({})




@app.route('/GetBroadcastSwitch', methods=['POST'])
def get_broadcast_switch():
    try:
        # data = request.get_json(force=True, silent=True)
        # region = data.get('region')
        
        print("[GetBroadcastSwitch] Проверка статуса объявлений")

        response = {
            "broadcast_switch": True  # True = Включено
        }

        return jsonify(response)

    except Exception as e:
        print(f"[GetBroadcastSwitch] Error: {e}")
        return jsonify({})
 
        
@app.route('/SetBroadcastSwitch', methods=['POST'])
def set_broadcast_switch():
    try:
        # user = get_user_from_request()
        # data = request.get_json(force=True, silent=True)
        # switch_state = data.get('broadcast_switch')

        print(f"[SetBroadcastSwitch] Игрок изменил настройки объявлений")

        # Просто возвращаем пустой JSON (успех), так как класс ответа обычно void/пустой
        return jsonify({})

    except Exception as e:
        print(f"[SetBroadcastSwitch] Error: {e}")
        return jsonify({})
        
        
# ==========================================
#           СИСТЕМА ДРУЗЕЙ (SOCIAL)
# ==========================================

# 1. Запрос списка ID друзей (упрощенный)
@app.route('/GetFriendIDs', methods=['POST'])
def get_friend_ids():
    try:
        print("[GetFriendIDs] Запрос ID всех друзей")
        # Возвращаем пустой список ID
        return jsonify({"friend_ids": []})
    except Exception as e:
        print(f"[GetFriendIDs] Error: {e}")
        return jsonify({})

# 2. Полный список друзей с их статусом (Online/Offline)
@app.route('/GetFriend', methods=['POST'])
def get_friend():
    try:
        print("[GetFriend] Запрос списка друзей с детализацией")
        # Структура AccountInfoWithPresence[] friends
        return jsonify({"friends": []})
    except Exception as e:
        print(f"[GetFriend] Error: {e}")
        return jsonify({})

# 3. Друзья с платформы (Facebook, VK, Google)
@app.route('/GetPlatformFriends', methods=['POST'])
def get_platform_friends():
    try:
        print("[GetPlatformFriends] Запрос друзей с платформы")
        return jsonify({"friends": []})
    except Exception as e:
        print(f"[GetPlatformFriends] Error: {e}")
        return jsonify({})

# 4. Рекомендованные друзья (кого добавить)
@app.route('/GetRecommendedFriend', methods=['POST'])
def get_recommended_friend():
    try:
        print("[GetRecommendedFriend] Запрос рекомендаций друзей")
        return jsonify({"friends": []})
    except Exception as e:
        print(f"[GetRecommendedFriend] Error: {e}")
        return jsonify({})

# 5. Список входящих запросов в друзья
@app.route('/GetFriendRequestList', methods=['POST'])
def get_friend_request_list():
    try:
        print("[GetFriendRequestList] Запрос списка заявок в друзья")
        # Обычно поле называется request_list или friend_requests
        # Отправляем оба варианта на всякий случай, пустой список
        return jsonify({
            "request_list": [],
            "friend_requests": []
        })
    except Exception as e:
        print(f"[GetFriendRequestList] Error: {e}")
        return jsonify({})

# 6. Поиск друга по ID (Бонус, чтобы работал поиск)
@app.route('/SearchFriendWithID', methods=['POST'])
def search_friend_with_id():
    try:
        data = request.get_json(force=True, silent=True)
        target_id = data.get('account_id')
        print(f"[SearchFriendWithID] Поиск игрока ID: {target_id}")
        
        # Пока возвращаем, что игрок не найден (null или пустой объект),
        # так как у нас нет базы других игроков в этом коде.
        # Если нужно вернуть фейкового друга, нужно формировать AccountInfo
        return jsonify({}) 
    except Exception as e:
        print(f"[SearchFriendWithID] Error: {e}")
        return jsonify({})

        
        
        
        
 # ==========================================
#           НАВЫКИ И СЛОТЫ (SKILLS)
# ==========================================

@app.route('/GetSkills', methods=['POST'])
def get_skills():
    try:
        print("[GetSkills] Запрос списка имеющихся навыков")
        # Возвращаем пустой список навыков (или можно добавить ID базовых навыков)
        return jsonify({"skills": []})
    except Exception as e:
        print(f"[GetSkills] Error: {e}")
        return jsonify({})

@app.route('/GetAvatarSkillSlots', methods=['POST'])
def get_avatar_skill_slots():
    try:
        print("[GetAvatarSkillSlots] Запрос слотов навыков персонажей")
        # Судя по твоему классу HTTP_GetSkillSlotCostRes, там поле infos
        # Отправляем пустой список, игра будет думать, что доп. слоты еще не открыты
        return jsonify({"infos": []})
    except Exception as e:
        print(f"[GetAvatarSkillSlots] Error: {e}")
        return jsonify({})
       
        
        
        
        
        
    # ==========================================
#           ОБЪЯВЛЕНИЯ (NEWS)
# ==========================================

@app.route('/GetAnnouncement', methods=['POST'])
def get_announcement():
    try:
        # data = request.get_json(force=True, silent=True)
        # lang = data.get('language') # Можно проверять язык (ru, en)
        
        print("[GetAnnouncement] Запрос новостей")

        # Создаем одно тестовое объявление
        news_item = {
            "id": 1,
            "title": "Welcome to Private Server",
            "desc": "Server is working successfully!",
            "image_url": "",             # Ссылка на картинку баннера (можно оставить пустым)
            "image_url_for_lobby": "",   # Картинка для малого баннера
            "link_url": "",              # Ссылка при клике
            "order_in_this_language": 1,
            "start_time": int(time.time()) - 3600,     # Началось час назад
            "end_time": int(time.time()) + 99999999,   # Закончится нескоро
            "region": "RU",
            "use_embedded_browser": False
        }

        # Возвращаем список объявлений
        response = {
            "announcements": [news_item]
        }

        return jsonify(response)

    except Exception as e:
        print(f"[GetAnnouncement] Error: {e}")
        return jsonify({"announcements": []})    
        
        
        
@app.route('/GetMatchStatsHistory', methods=['POST'])
def get_match_stats_history():
    try:
        print("[GetMatchStatsHistory] Запрос истории матчей")
        
        # match_stats_list - это массив. Отправляем пустой.
        response = {
            "match_stats_list": []
        }
        
        return jsonify(response)

    except Exception as e:
        print(f"[GetMatchStatsHistory] Error: {e}")
        return jsonify({})


@app.route('/GetAccountMatchStats', methods=['POST'])
def get_account_match_stats():
    try:
        # data = request.get_json(force=True, silent=True)
        # match_id = data.get('match_id')
        
        print("[GetAccountMatchStats] Запрос деталей конкретного матча")

        # Возвращаем пустые строки, так как в C# это string
        response = {
            "income": "",       
            "match_stats": ""   
        }
        
        return jsonify(response)

    except Exception as e:
        print(f"[GetAccountMatchStats] Error: {e}")
        return jsonify({})



@app.route('/Billboard', methods=['POST'])
def get_billboard():
    try:
        print("[Billboard] Запрос данных для билборда")

        # Создаем тестовое сообщение для билборда
        billboard_items = [
            {
                "id": 1,
                "desc": "Welcome to Server",  # Текст, который будет показан
                "enabled": 1                  # 1 = Включено, 0 = Выключено
            }
        ]

        # В большинстве версий этой игры список называется "billboard_list"
        response = {
            "billboard_list": billboard_items
        }

        return jsonify(response)

    except Exception as e:
        print(f"[Billboard] Error: {e}")
        return jsonify({})


# ==========================================
#           РЕКЛАМА (ADS)
# ==========================================

@app.route('/GetAds', methods=['POST'])
def get_ads():
    try:
        # data = request.get_json(force=True, silent=True)
        # lang = data.get('language') # Можно учитывать язык
        
        print("[GetAds] Запрос списка рекламы")

        # Возвращаем пустой список, так как реклама нам пока не нужна
        response = {
            "advert_items": [] 
        }

        return jsonify(response)

    except Exception as e:
        print(f"[GetAds] Error: {e}")
        return jsonify({})







# ==========================================
#           ELITE PASS SYSTEM (FIXED)
# ==========================================

# 1. Покупка уровней (Badges)
@app.route('/EPPurchaseBadge', methods=['POST'])
def ep_purchase_badge_handler():  # <-- Я изменил имя функции
    try:
        data = request.get_json(force=True, silent=True)
        count = data.get('count')
        print(f"[EP] Покупка {count} значков")
        
        cursor.execute("UPDATE users SET badge_cnt = badge_cnt + ? WHERE account_id = ?", (count, account_id))
        conn.commit()
        return jsonify({})
    except Exception as e:
        print(f"[EP] Error: {e}")
        return jsonify({})

# 2. Покупка пропуска
@app.route('/EPPurchase', methods=['POST'])
def ep_purchase_handler():  # <-- Я изменил имя функции
    try:
        data = request.get_json(force=True, silent=True)
        is_bundle = data.get('is_bundle')
        print(f"[EP] Покупка Elite Pass (Bundle: {is_bundle})")

        cursor.execute("UPDATE users SET has_elite_pass = 1 WHERE account_id = ?", (account_id,))
        conn.commit()
        return jsonify({})
    except Exception as e:
        print(f"[EP] Error: {e}")
        return jsonify({})

# 3. Забрать награду
@app.route('/EPClaimReward', methods=['POST'])
def ep_claim_reward_handler():  # <-- Я изменил имя функции
    try:
        data = request.get_json(force=True, silent=True)
        unlock_id = data.get('unlock_id')
        is_ep = data.get('is_ep')
        print(f"[EP] Забрана награда ID: {unlock_id} (Elite: {is_ep})")
        
        return jsonify({})
    except Exception as e:
        print(f"[EP] Error: {e}")
        return jsonify({})

# 4. Забрать значки за миссии
@app.route('/EPClaimBadge', methods=['POST'])
def ep_claim_challenge_handler():  # <-- Я изменил имя функции
    try:
        data = request.get_json(force=True, silent=True)
        challenge_id = data.get('challenge_id')
        print(f"[EP] Выполнен челлендж {challenge_id}")
        
        return jsonify({})
    except Exception as e:
        print(f"[EP] Error: {e}")
        return jsonify({})






# ==========================================
#           ЧАТ (CHAT SYSTEM)
# ==========================================

@app.route('/Chat', methods=['POST'])
def chat_msg():
    try:
        data = request.get_json(force=True, silent=True)
        
        account_id = data.get('account_id')
        region = data.get('region')
        raw_data = data.get('data') # Это Base64 строка
        
        print(f"[Chat] Сообщение от игрока ID: {account_id} (Region: {region})")
        
        # Если хочешь попробовать увидеть, что внутри (не всегда читаемо):
        # if raw_data:
        #     decoded_bytes = base64.b64decode(raw_data)
        #     print(f"[Chat] Raw bytes: {decoded_bytes}")

        # Обычно сервер просто подтверждает получение пустым ответом.
        # Само сообщение нужно рассылать другим игрокам через отдельную систему (если она есть)
        # или сохранять в историю.
        
        return jsonify({})

    except Exception as e:
        print(f"[Chat] Error: {e}")
        return jsonify({})




import time

# ==========================================
#           ACTIVITY DESCRIPTION
# ==========================================

@app.route('/GetActivityDesc', methods=['POST'])
def get_activity_desc_handler():
    try:
        data = request.get_json(force=True, silent=True)
        # account_id = data.get('account_id')
        
        print(f"[Activity] Запрос описания событий (GetActivityDesc)")

        current_time = str(int(time.time()))
        end_time = str(int(time.time()) + 2592000) # +30 дней

        # Создаем пример одного события (чтобы меню не было пустым)
        # Все поля взяты из твоего C# класса ActivityDesc
        event_example = {
            "group_id": 1,
            "activity_id": 1001,        # ID события
            "activity_type": 1,         # Тип события
            "sort_id": 1,
            "is_process_show": 1,
            "act_tag": 0,
            "gos_pos": 1,
            "start_time": current_time, # Время начала (строка)
            "end_time": end_time,       # Время конца (строка)
            "show_time": current_time,  # Время отображения иконки
            
            "circle_type": 0,           # Тип цикла (ежедневно/разово)
            
            # Условия (прекондишны) - ставим 0, чтобы было доступно всем
            "pre_cdt_type1": 0, "pre_cdt_value1": 0,
            "pre_cdt_type2": 0, "pre_cdt_value2": 0,
            "pre_cdt_type3": 0, "pre_cdt_value3": 0,
            "pre_cdt_type4": 0, "pre_cdt_value4": 0,
            "pre_cdt_type5": 0, "pre_cdt_value5": 0,
            
            "cdt_type": 0,              # Основное условие
            "cdt_value": 0,
            
            "awards": [],               # Список наград (AwardDesc)
            "exchange_item": None       # Предмет обмена (если есть)
        }

        # Возвращаем список описаний
        # В C# это ActivityMsg, скорее всего там массив 'activity_descs' или просто список
        response_data = {
            "activity_descs": [event_example]
        }
        
        return jsonify(response_data)

    except Exception as e:
        print(f"[GetActivityDesc] Error: {e}")
        # В случае ошибки возвращаем пустой список
        return jsonify({"activity_descs": []})





# ==========================================
#           ACTIVITY INFO (Прогресс)
# ==========================================

@app.route('/GetActivityInfo', methods=['POST'])
def get_activity_info_handler():
    try:
        # Клиент запрашивает статус выполнения событий (прогресс)
        print(f"[Activity] Запрос инфо о прогрессе (GetActivityInfo)")

        # Создаем пример состояния для события с ID 1001
        # Поля взяты из твоего C# класса ActivityUpdateInfo:
        # id (uint), data (uint), state (uint), context (string)
        
        activity_state = {
            "id": 1001,       # ID события (должен совпадать с тем, что в GetActivityDesc)
            "data": 0,        # Прогресс (например, 5 из 10 убийств)
            "state": 0,       # Статус (0 = в процессе, 1 = выполнено/можно забрать, 2 = забрано)
            "context": ""     # Дополнительный контекст (обычно пусто)
        }

        # Формируем ответ. Важно: название поля "activitys" (как в C# коде)
        response_data = {
            "activitys": [activity_state]
        }
        
        return jsonify(response_data)

    except Exception as e:
        print(f"[GetActivityInfo] Error: {e}")
        # Если ошибка, возвращаем пустой массив, чтобы игра не зависла
        return jsonify({"activitys": []})


# ==========================================
#           LEADERBOARD & RANK SETTINGS
# ==========================================

@app.route('/SetShowRank', methods=['POST'])
def set_show_rank_handler():
    try:
        data = request.get_json(force=True, silent=True)
        season_id = data.get('season_id')
        show_rank = data.get('show_rank') # Это boolean (True/False)
        
        # account_id нужно брать из токена авторизации, здесь для примера пропускаем
        
        print(f"[Rank] Установка отображения ранга: {show_rank} (Сезон: {season_id})")

        # TODO: Сохранить настройку в БД (таблица users)
        # cursor.execute("UPDATE users SET show_rank = ? WHERE account_id = ...", (1 if show_rank else 0,))
        
        # Ответ (SetShowRankRes) требует поле "show_rank"
        return jsonify({"show_rank": show_rank})

    except Exception as e:
        print(f"[SetShowRank] Error: {e}")
        # В случае ошибки возвращаем false
        return jsonify({"show_rank": False})

@app.route('/Leaderboard', methods=['POST'])
def leaderboard_handler():
    try:
        data = request.get_json(force=True, silent=True) or {}
        page_index = data.get('page_index', 0)
        
        # Получаем токен для поиска "себя"
        client_token = request.headers.get('Token') 
        if not client_token and 'LAST_ACTIVE_TOKEN' in globals():
            client_token = LAST_ACTIVE_TOKEN

        logger.info(f"🏆 [Leaderboard] Запрос топа. Стр: {page_index}")

        conn = sqlite3.connect('game.db')
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()

        # --- СПИСОК (ITEMS) ---
        limit = 50
        offset = page_index * limit
        
        cursor.execute('''
            SELECT * FROM users 
            ORDER BY exp DESC 
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        
        rows = cursor.fetchall()
        items_list = []
        
        for row in rows:
            # Превращаем строку БД в словарь, чтобы работал метод .get()
            user = dict(row)
            
            # Твоя логика: ранг равен уровню
            rank_val = int(user.get('rang', 1))

            items_list.append({
                "account_id": user.get('account_id'),
                "nickname": user.get('nickname'),
                "gender": user.get('gender', 1),
                "level": user.get('level', 1),
                "exp": user.get('exp', 0),
                "rank_score": user.get('exp', 0),
                "rank": rank_val, # <--- ТУТ КАК ТЫ ПРОСИЛ
                "avatar_id": user.get('avatar_id', 101000006),
                "region": user.get('region', "RU"),
                "badge_cnt": user.get('badge_cnt', 0),
                "badge_id": user.get('badge_id', 0)
            })

        # --- О СЕБЕ (SELF) ---
        self_data = {}
        if client_token:
            cursor.execute("SELECT * FROM users WHERE token = ?", (client_token,))
            me_row = cursor.fetchone()
            
            if me_row:
                user = dict(me_row)
                rank_val = int(user.get('level', 1))
                
                self_data = {
                    "account_id": user.get('account_id'),
                    "nickname": user.get('nickname'),
                    "gender": user.get('gender', 1),
                    "level": user.get('level', 1),
                    "exp": user.get('exp', 0),
                    "rank_score": user.get('exp', 0),
                    "rank": rank_val, # <--- ТУТ ТОЖЕ
                    "avatar_id": user.get('avatar_id'),
                    "region": user.get('region', "RU"),
                    "badge_cnt": user.get('badge_cnt', 0),
                    "badge_id": user.get('badge_id', 0)
                }

        # Если self пустой
        if not self_data:
            self_data = {
                "account_id": 0, "nickname": "", "rank": 1, "level": 1, 
                "exp": 0, "avatar_id": 101000006, "region": "RU"
            }

        conn.close()

        return jsonify({
            "items": items_list,
            "self": self_data
        })

    except Exception as e:
        logger.error(f"[Leaderboard] Error: {e}")
        return jsonify({"items": [], "self": {}}), 500

















































if __name__ == '__main__':
    init_db()
    print("=== SERVER STARTED (FALLBACK MODE ENABLED) ===")
    app.run(host='0.0.0.0', port=8080, debug=True)