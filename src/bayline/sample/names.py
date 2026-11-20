"""Fixed fictional names and address fragments."""

MERCHANTS = ("Nile Loom", "Delta Gadgets", "Corniche Home", "Willow Textiles",
    "Meadow Goods", "Grove Homewares", "Cedar Clothing", "Harbor Stationery",
    "Orchard Lighting", "Palm Crafts", "Garden Linens", "Brook Kitchenware",
    "Fern Accessories", "Olive Ceramics", "Ravine Tools", "Maple Fabrics",
    "Sandbar Furnishings", "Acacia Books", "Kelp Supplies", "Rose Gifts")
ANCHOR_FIRST_NAMES = ("Tarek", "Nadia", "Hassan", "Laila", "Mona", "Adel", "Salma", "Amr",
               "Rana", "Mahmoud", "Heba", "Youssef", "Rania", "Ehab", "Dalia")
ANCHOR_LAST_NAMES = ("Sorour", "Farouk", "Ibrahim", "Kamal", "Gaber", "Shawky", "Youssef", "Lotfy",
              "Helmy", "Fathy", "Sami", "Nabil", "Aziz", "Morsi", "Samir")
FIRST_NAMES = ("Amina", "Basma", "Dina", "Eman", "Farida", "Ghada", "Hala", "Iman",
    "Jana", "Karima", "Lamia", "Mai", "Nermine", "Ola", "Passant", "Rehab",
    "Sahar", "Tasneem", "Wafaa", "Yasmin", "Zeinab", "Aya", "Doaa", "Esraa",
    "Fatma", "Habiba", "Inas", "Jihan", "Kholoud", "Lubna", "Marwa", "Nada",
    "Omayma", "Radwa", "Sherine", "Thanaa", "Walaa", "Yara", "Zahra", "Ashraf",
    "Bassem", "Essam", "Fadi", "Gamal", "Hatem", "Ismail", "Jalal", "Khaled",
    "Loay", "Mazen", "Nader", "Osama", "Qassem", "Raouf", "Sherif", "Tamer",
    "Wael", "Yehia", "Zakaria", "Anas", "Badr", "Hazem", "Mostafa", "Ramy")
LAST_NAMES = ("Abdeen", "Bahgat", "Dawood", "Elwan", "Fahmy", "Ghanem", "Hafez", "Iskander",
    "Jaber", "Karam", "Labib", "Mahfouz", "Naggar", "Othman", "Qadri", "Ragab",
    "Sabry", "Taher", "Wahba", "Younan", "Zaki", "Amer", "Badawi", "Diab",
    "Elgindy", "Fikry", "Gohar", "Hamdy", "Iskandar", "Kassem", "Khattab", "Madkour",
    "Beshir", "Okasha", "Qutb", "Rashad", "Sakr", "Tawfik", "Wassef", "Yassin",
    "Zahran", "Attia", "Habib", "Hussein", "Ezzat", "Fouad", "Ghoneim", "Hegazy",
    "Khalil", "Lasheen", "Mekky", "Nouh", "Omran", "Rizk", "Shaker", "Talaat",
    "Waly", "Younis", "Zidan", "Awad", "Bakry", "Desouky", "Salem", "Haroun")
STREETS = ("First Street", "Second Street", "Third Street", "Fourth Street",
    "Rose Street", "Jasmine Street", "Lily Street", "Iris Street",
    "Palm Street", "Olive Street", "Cedar Street", "Acacia Street")
PHONE_PREFIXES = {"EG": "+20 100", "AE": "+971 50", "SA": "+966 50", "JO": "+962 79"}


def customer_phone(country, rng, used):
    """Choose an unused number within the country's fictional 555-0 block."""
    while True:
        phone = f"{PHONE_PREFIXES[country]} 555 0{rng.randrange(1000):03}"
        if phone not in used:
            used.add(phone)
            return phone


STAFF = (
    ("lina.haddad", "Lina Haddad", "Engineering lead", "customer_platform"),
    ("yousef.darwish", "Yousef Darwish", "Senior engineer", "customer_platform"),
    ("sana.barakat", "Sana Barakat", "Staff engineer", "customer_platform"),
    ("mira.saad", "Mira Saad", "QA engineer", "customer_platform"),
    ("huda.al-mansoori", "Huda Al-Mansoori", "Head of Customer Service", "customer_service"),
    ("reem.adel", "Reem Adel", "Desk shift lead", "customer_service"),
    ("karim.nassar", "Karim Nassar", "Desk agent", "customer_service"),
    ("dina.fawzy", "Dina Fawzy", "Desk agent", "customer_service"),
    ("omar.elbanna", "Omar Elbanna", "Desk agent", "customer_service"),
)
