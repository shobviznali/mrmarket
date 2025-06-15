import telebot
import os
from dotenv import load_dotenv
from woocommerce import API
from openai import OpenAI
import itertools


jst = 1
# Загружаем .env
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WC_URL = os.getenv("WOOCOMMERCE_URL")
WC_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY")
WC_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET")

bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# WooCommerce API
wcapi = API(
    url=WC_URL,
    consumer_key=WC_KEY,
    consumer_secret=WC_SECRET,
    version="wc/v3"
)

# Транслитерация с русского/английского на армянский
transliteration_map = {
    'a': ['ա'], 'b': ['բ'], 'g': ['գ'], 'd': ['դ'],
    'e': ['ե', 'է'], 'z': ['զ'], 't': ['թ', 'տ'], 'i': ['ի'],
    'l': ['լ'], 'kh': ['խ'], 'k': ['կ', 'ք'], 'h': ['հ'], 'j': ['ջ'],
    'sh': ['շ'], 'ch': ['չ', 'ճ'], 'zh': ['ժ'], 'x': ['խ', 'ղ'],
    'c': ['ց', 'ք', 'ծ'], 'm': ['մ'], 'y': ['յ'], 'n': ['ն'],
    'o': ['օ', 'ո'], 'p': ['պ', 'փ'], 'r': ['ր', 'ռ'], 's': ['ս'],
    'v': ['վ'], 'u': ['ու'], 'f': ['ֆ'], 'q': ['ք'], 'ev': ['և'],
    'ts': ['ց', 'ծ'], 'ye': ['ե'], 'gh': ['ղ'], 'vo': ['ո']
}


# Обратная транслитерация с армянского на английский
reverse_map = {
    'ա': 'a', 'բ': 'b', 'գ': 'g', 'դ': 'd', 'ե': 'e', 'է': 'e', 'զ': 'z',
    'տ': 't', 'թ': 't', 'ի': 'i', 'լ': 'l', 'խ': 'kh', 'կ': 'k', 'ք': 'k',
    'հ': 'h', 'ձ': 'dz', 'ժ': 'zh', 'ջ': 'j', 'շ': 'sh', 'չ': 'ch', 'ճ': 'ch',
    'ղ': 'gh', 'ց': 'ts', 'ծ': 'ts', 'մ': 'm', 'յ': 'y', 'ն': 'n',
    'օ': 'o', 'ո': 'vo', 'պ': 'p', 'փ': 'p', 'ր': 'r', 'ռ': 'r',
    'ս': 's', 'վ': 'v', 'ու': 'u', 'ֆ': 'f', 'և': 'ev'
}

def generate_transliterations(text):
    text = text.lower()
    variants = [[]]

    i = 0
    while i < len(text):
        matched = False
        for l in (3, 2, 1):  # Пробуем 3-, 2- и 1-буквенные комбинации
            part = text[i:i + l]
            if part in transliteration_map:
                replacements = transliteration_map[part]
                variants[-1].append(replacements)
                i += l
                matched = True
                break
        if not matched:
            variants[-1].append([text[i]])  # Неизвестный символ — оставить как есть
            i += 1

    combinations = itertools.product(*variants[-1])
    return [''.join(c) for c in combinations]


def transliterate_to_armenian(text):
    text = text.lower()
    result = ''
    i = 0
    while i < len(text):
        two_letter = text[i:i + 2]
        if two_letter in transliteration_map:
            result += transliteration_map[two_letter][0]
            i += 2
            continue
        one_letter = text[i]
        if one_letter in transliteration_map:
            result += transliteration_map[one_letter][0]
        else:
            result += one_letter
        i += 1
    return result


def transliterate_to_english(text):
    result = ''
    i = 0
    while i < len(text):
        if text[i:i + 2] == 'ու':
            result += 'u'
            i += 2
            continue
        result += reverse_map.get(text[i], text[i])
        i += 1
    return result

def search_product_multi(name_original, _):
    search_terms = set()
    search_terms.add(name_original)

    if any(char in reverse_map for char in name_original):
        name_english = transliterate_to_english(name_original)
        search_terms.add(name_english)

    armenian_variants = generate_transliterations(name_original)
    search_terms.update(armenian_variants)

    all_results = []
    seen_names = set()

    for term in search_terms:
        try:
            response = wcapi.get("products", params={"search": term})
            response.raise_for_status()
        except Exception as e:
            print(f"[WooCommerce Error] {e}")
            continue

        data = response.json()
        if data:
            for product in data:
                product_name = product["name"]
                if product_name not in seen_names:
                    seen_names.add(product_name)
                    all_results.append({
                        "name": product_name,
                        "price": product.get("price", "չի նշված"),
                        "link": product.get("permalink", "")
                    })
            # Нашли результаты — прерываем дальше искать
            break

    if not all_results:
        return f"Տվյալ ապրանքը `{name_original}` չի գտնվել 😕", []

    return None, all_results[:3]


def extract_product_name(user_input):
    prompt = f"""
Դու արհեստական բանականություն ես, որը օգնում է դուրս բերել ապրանքի անունը հաճախորդի նամակից
Նամակը: "{user_input}"

Ответь только названием товара, которое нужно найти на сайте. 
Не добавляй ничего лишнего, только название.
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    extracted_name = response.choices[0].message.content.strip()
    armenian_name = transliterate_to_armenian(extracted_name)
    print(f"[GPT Extracted] '{extracted_name}' → [Armenian] '{armenian_name}'")
    return extracted_name, armenian_name

def generate_gpt_response(user_question, products):
    product_info = "\n".join([
        f"{p['name']} — {p['price']} դրամ — {p['link']}"
        for p in products
    ])

    prompt = f"""
Դու խանութի օնլայն կոնսուլտանտ ես։ Ահա թե ինչ է հարցրել հաճախորդը "{user_question}"

Ահա թե ինչ ենք գտել
{product_info}

Պատասխանիր բարեհամբույթ, ասես թե դու կոնսուլտանտ ես և առաջարկիր ապրանքները։ Առանց ավելորդ ինֆորմացիայի։ Ուղարկիր հղումները։ Վերջում միայն նշիր՝ ունի արդյոք այլ հարցեր հաճախորդը։
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
    )

    return response.choices[0].message.content

start_message = "Ողջույն։ Ես MR Market-ի օնլայն խորհրդատուն եմ։ Ես կօգնեմ Ձեզ արագ գտնել ցանկալի ապրանքը։"

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, start_message)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_query = message.text.strip()

    extracted_name, armenian_name = extract_product_name(user_query)
    error, results = search_product_multi(extracted_name, armenian_name)

    if error:
        bot.send_message(message.chat.id, 'Խնդրում ենք գրել ապրանքի անունը')
        return

    gpt_reply = generate_gpt_response(user_query, results)
    bot.send_message(message.chat.id, gpt_reply, parse_mode='Markdown')

    search_link = f"https://mrmarket.am/?s={extracted_name}&post_type=product"
    bot.send_message(message.chat.id, f"Այլ արդյունքների համար անցեք հետևյալ հղումով {search_link}")

print("Բոտը պատրաստ է 🚀")
bot.polling()

