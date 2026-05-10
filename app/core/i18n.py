from typing import Any

# All strings keyed by locale
_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # General
        "welcome": "👋 Welcome to <b>Q1 eSIM</b>!\n\nInstant eSIM delivery to your phone — no plastic, no waiting.\n\nUse the menu below to get started.",
        "welcome_back": "👋 Welcome back, <b>{name}</b>!",
        "choose_action": "Choose an action:",
        "error_generic": "❌ Something went wrong. Please try again.",
        "cancelled": "❌ Cancelled.",
        "back": "◀️ Back",
        "close": "✖ Close",
        "loading": "⏳ Loading...",
        # Main menu
        "menu_buy": "🛒 Buy eSIM",
        "menu_my_esims": "📱 My eSIMs",
        "menu_profile": "👤 Profile",
        "menu_support": "💬 Support",
        "menu_referral": "🎁 Referral",
        "menu_language": "🌐 Language",
        # Country selection
        "select_country": "🌍 <b>Select a country</b>\n\nChoose the country where you need mobile data:",
        "country_not_found": "❌ Country not found.",
        "no_countries": "❌ No countries available at the moment.",
        # Plan selection
        "select_plan": "📋 <b>Plans for {country} {flag}</b>\n\nChoose a data plan:",
        "plan_card": "📦 <b>{name}</b>\n📊 Data: <b>{data_gb} GB</b>\n📅 Duration: <b>{days} days</b>\n💰 Price: <b>${price}</b>",
        "no_plans": "❌ No plans available for this country.",
        # Order & payment
        "order_confirm": (
            "🛒 <b>Order Summary</b>\n\n"
            "🌍 Country: <b>{country}</b>\n"
            "📦 Plan: <b>{plan}</b>\n"
            "📊 Data: <b>{data_gb} GB</b>\n"
            "📅 Duration: <b>{days} days</b>\n"
            "💰 Amount: <b>${amount}</b>\n\n"
            "Proceed to payment?"
        ),
        "btn_pay": "💳 Pay ${amount}",
        "btn_cancel": "✖ Cancel",
        "payment_created": "✅ Payment created!\n\nClick the button below to pay securely:",
        "btn_pay_now": "💳 Pay Now",
        "payment_pending": "⏳ Waiting for payment...",
        "payment_success": "✅ Payment successful!",
        "payment_failed": "❌ Payment failed. Please try again.",
        # eSIM delivery
        "esim_ready": (
            "🎉 <b>Your eSIM is ready!</b>\n\n"
            "📱 <b>ICCID:</b> <code>{iccid}</code>\n"
            "🔑 <b>Activation Code:</b>\n<code>{activation_code}</code>\n"
            "🔗 <b>LPA:</b>\n<code>{lpa}</code>\n\n"
            "📸 Scan the QR code below to activate:"
        ),
        "esim_provisioning": "⏳ Activating your eSIM, please wait...",
        # My eSIMs
        "my_esims_empty": "📭 You don't have any eSIMs yet.\n\nUse <b>Buy eSIM</b> to get started!",
        "my_esims_header": "📱 <b>Your eSIMs</b>\n\nYou have <b>{count}</b> eSIM(s):",
        "esim_detail": (
            "📱 <b>eSIM Details</b>\n\n"
            "📋 ICCID: <code>{iccid}</code>\n"
            "🌍 Country: {country}\n"
            "📦 Plan: {plan}\n"
            "📊 Status: {status}\n"
            "💾 Data used: {used_mb} MB / {total_mb} MB\n"
            "📅 Expires: {expires_at}"
        ),
        "esim_status_active": "🟢 Active",
        "esim_status_inactive": "🔴 Inactive",
        "esim_status_expired": "⚫ Expired",
        "btn_show_qr": "📸 Show QR",
        "btn_check_status": "🔄 Refresh Status",
        # Profile
        "profile": (
            "👤 <b>Your Profile</b>\n\n"
            "🆔 ID: <code>{telegram_id}</code>\n"
            "👤 Name: {name}\n"
            "💰 Balance: <b>${balance}</b>\n"
            "🛒 Total spent: <b>${total_spent}</b>\n"
            "📱 eSIMs purchased: <b>{esim_count}</b>\n"
            "🗓 Member since: {since}"
        ),
        # Referral
        "referral": (
            "🎁 <b>Referral Program</b>\n\n"
            "Invite friends and earn <b>{percent}%</b> from every purchase!\n\n"
            "🔗 Your referral link:\n<code>{link}</code>\n\n"
            "👥 Friends invited: <b>{count}</b>\n"
            "💰 Total earned: <b>${earned}</b>"
        ),
        "btn_copy_link": "📋 Copy Link",
        # Admin
        "admin_stats": (
            "📊 <b>Admin Statistics</b>\n\n"
            "👥 Total users: <b>{total_users}</b>\n"
            "✅ Active users: <b>{active_users}</b>\n"
            "📱 eSIMs sold: <b>{esims_sold}</b>\n"
            "💰 Revenue today: <b>${today}</b>\n"
            "💰 Revenue this month: <b>${month}</b>\n"
            "💰 Total revenue: <b>${total}</b>"
        ),
        "not_admin": "⛔ You don't have admin access.",
        "admin_panel_header": "🔐 <b>Admin Panel</b>\n\nWelcome, {name}!",
        "admin_btn_stats": "📊 Statistics",
        "admin_btn_users": "👥 Users",
        "admin_btn_esims": "📱 eSIMs",
        "admin_btn_countries": "🌍 Countries",
        "admin_btn_plans": "📦 Plans",
        "admin_btn_broadcast": "📢 Broadcast",
        "admin_btn_logs": "📋 Logs",
        "admin_btn_sync": "🔄 Sync Catalog",
        "admin_btn_exit": "🚪 Back to Menu",
        "menu_admin": "🔐 Admin Panel",
        "menu_open_app": "Open Store",
        # Support
        "support_message": "💬 <b>Support</b>\n\nFor help, contact: @q1esim_support\n\nOr describe your issue and we'll get back to you:",
        "support_sent": "✅ Your message has been forwarded to support.",
    },
    "ru": {
        # General
        "welcome": "👋 Добро пожаловать в <b>Q1 eSIM</b>!\n\nМгновенная доставка eSIM — без пластика и ожидания.\n\nВоспользуйтесь меню ниже.",
        "welcome_back": "👋 С возвращением, <b>{name}</b>!",
        "choose_action": "Выберите действие:",
        "error_generic": "❌ Что-то пошло не так. Попробуйте ещё раз.",
        "cancelled": "❌ Отменено.",
        "back": "◀️ Назад",
        "close": "✖ Закрыть",
        "loading": "⏳ Загрузка...",
        # Main menu
        "menu_buy": "🛒 Купить eSIM",
        "menu_my_esims": "📱 Мои eSIM",
        "menu_profile": "👤 Профиль",
        "menu_support": "💬 Поддержка",
        "menu_referral": "🎁 Реферальная программа",
        "menu_language": "🌐 Язык",
        # Country selection
        "select_country": "🌍 <b>Выберите страну</b>\n\nВыберите страну, где вам нужен мобильный интернет:",
        "country_not_found": "❌ Страна не найдена.",
        "no_countries": "❌ Страны временно недоступны.",
        # Plan selection
        "select_plan": "📋 <b>Тарифы для {country} {flag}</b>\n\nВыберите тарифный план:",
        "plan_card": "📦 <b>{name}</b>\n📊 Данные: <b>{data_gb} ГБ</b>\n📅 Срок: <b>{days} дней</b>\n💰 Цена: <b>${price}</b>",
        "no_plans": "❌ Тарифы для этой страны недоступны.",
        # Order & payment
        "order_confirm": (
            "🛒 <b>Ваш заказ</b>\n\n"
            "🌍 Страна: <b>{country}</b>\n"
            "📦 Тариф: <b>{plan}</b>\n"
            "📊 Данные: <b>{data_gb} ГБ</b>\n"
            "📅 Срок: <b>{days} дней</b>\n"
            "💰 Сумма: <b>${amount}</b>\n\n"
            "Перейти к оплате?"
        ),
        "btn_pay": "💳 Оплатить ${amount}",
        "btn_cancel": "✖ Отмена",
        "payment_created": "✅ Платёж создан!\n\nНажмите кнопку ниже для безопасной оплаты:",
        "btn_pay_now": "💳 Оплатить",
        "payment_pending": "⏳ Ожидание оплаты...",
        "payment_success": "✅ Оплата прошла успешно!",
        "payment_failed": "❌ Ошибка оплаты. Попробуйте ещё раз.",
        # eSIM delivery
        "esim_ready": (
            "🎉 <b>Ваш eSIM готов!</b>\n\n"
            "📱 <b>ICCID:</b> <code>{iccid}</code>\n"
            "🔑 <b>Код активации:</b>\n<code>{activation_code}</code>\n"
            "🔗 <b>LPA:</b>\n<code>{lpa}</code>\n\n"
            "📸 Отсканируйте QR-код ниже для активации:"
        ),
        "esim_provisioning": "⏳ Активируем ваш eSIM, пожалуйста подождите...",
        # My eSIMs
        "my_esims_empty": "📭 У вас ещё нет eSIM.\n\nВоспользуйтесь <b>Купить eSIM</b>!",
        "my_esims_header": "📱 <b>Ваши eSIM</b>\n\nУ вас <b>{count}</b> eSIM:",
        "esim_detail": (
            "📱 <b>Детали eSIM</b>\n\n"
            "📋 ICCID: <code>{iccid}</code>\n"
            "🌍 Страна: {country}\n"
            "📦 Тариф: {plan}\n"
            "📊 Статус: {status}\n"
            "💾 Использовано: {used_mb} МБ / {total_mb} МБ\n"
            "📅 Действует до: {expires_at}"
        ),
        "esim_status_active": "🟢 Активен",
        "esim_status_inactive": "🔴 Неактивен",
        "esim_status_expired": "⚫ Истёк",
        "btn_show_qr": "📸 Показать QR",
        "btn_check_status": "🔄 Обновить статус",
        # Profile
        "profile": (
            "👤 <b>Ваш профиль</b>\n\n"
            "🆔 ID: <code>{telegram_id}</code>\n"
            "👤 Имя: {name}\n"
            "💰 Баланс: <b>${balance}</b>\n"
            "🛒 Потрачено: <b>${total_spent}</b>\n"
            "📱 Куплено eSIM: <b>{esim_count}</b>\n"
            "🗓 С нами с: {since}"
        ),
        # Referral
        "referral": (
            "🎁 <b>Реферальная программа</b>\n\n"
            "Приглашайте друзей и получайте <b>{percent}%</b> с каждой покупки!\n\n"
            "🔗 Ваша реферальная ссылка:\n<code>{link}</code>\n\n"
            "👥 Приглашено друзей: <b>{count}</b>\n"
            "💰 Заработано: <b>${earned}</b>"
        ),
        "btn_copy_link": "📋 Скопировать ссылку",
        # Admin
        "admin_stats": (
            "📊 <b>Статистика</b>\n\n"
            "👥 Всего пользователей: <b>{total_users}</b>\n"
            "✅ Активных: <b>{active_users}</b>\n"
            "📱 Продано eSIM: <b>{esims_sold}</b>\n"
            "💰 Доход сегодня: <b>${today}</b>\n"
            "💰 Доход за месяц: <b>${month}</b>\n"
            "💰 Всего доход: <b>${total}</b>"
        ),
        "not_admin": "⛔ У вас нет прав администратора.",
        "admin_panel_header": "🔐 <b>Админ-панель</b>\n\nДобро пожаловать, {name}!",
        "admin_btn_stats": "📊 Статистика",
        "admin_btn_users": "👥 Пользователи",
        "admin_btn_esims": "📱 eSIM",
        "admin_btn_countries": "🌍 Страны",
        "admin_btn_plans": "📦 Тарифы",
        "admin_btn_broadcast": "📢 Рассылка",
        "admin_btn_logs": "📋 Логи",
        "admin_btn_sync": "🔄 Синхр. каталог",
        "admin_btn_exit": "🚪 В меню",
        "menu_admin": "🔐 Админ-панель",
        "menu_open_app": "Открыть магазин",
        # Support
        "support_message": "💬 <b>Поддержка</b>\n\nДля помощи: @q1esim_support\n\nОпишите вашу проблему:",
        "support_sent": "✅ Ваше сообщение отправлено в поддержку.",
    },
}


def t(key: str, lang: str = "en", **kwargs: Any) -> str:
    strings = _STRINGS.get(lang) or _STRINGS["en"]
    text = strings.get(key) or _STRINGS["en"].get(key) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text
