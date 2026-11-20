-- UTC timestamps, whole piastres, and explicit enumerations.
CREATE TABLE IF NOT EXISTS meta (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staff (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    team TEXT NOT NULL  CHECK(team IN ('customer_platform','customer_service'))
);

CREATE TABLE IF NOT EXISTS customers (
    id TEXT NOT NULL PRIMARY KEY,
    kind TEXT NOT NULL  CHECK(kind IN ('merchant','recipient')),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE CHECK(email = lower(email)),
    phone TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL  CHECK(country IN ('EG','AE','SA','JO')),
    returns_plan INTEGER NOT NULL CHECK(returns_plan IN (0,1)) CHECK(kind = 'merchant' OR returns_plan = 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shipments (
    tracking_number TEXT NOT NULL PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES customers(id),
    recipient_id TEXT NOT NULL REFERENCES customers(id),
    service TEXT NOT NULL  CHECK(service IN ('express','standard','economy')),
    lane TEXT NOT NULL  CHECK(lane IN ('domestic','international')),
    origin_city TEXT NOT NULL CHECK(origin_city IN ('Alexandria','Cairo')),
    destination_city TEXT NOT NULL,
    destination_country TEXT NOT NULL  CHECK(destination_country IN ('EG','AE','SA','JO')),
    destination_tz TEXT NOT NULL,
    address_line TEXT NOT NULL,
    goods_category TEXT NOT NULL  CHECK(goods_category IN ('general','clothing','electronics','documents','furniture','cosmetics','perishable','battery','hazardous')),
    goods_description TEXT NOT NULL,
    pieces INTEGER NOT NULL CHECK(typeof(pieces) = 'integer') CHECK(pieces BETWEEN 1 AND 10),
    weight_kg REAL NOT NULL CHECK(weight_kg > 0 AND weight_kg <= 30 * pieces AND round(weight_kg, 1) = weight_kg),
    declared_value_piastres INTEGER NOT NULL CHECK(typeof(declared_value_piastres) = 'integer') CHECK(declared_value_piastres >= 0),
    insured INTEGER NOT NULL CHECK(insured IN (0,1)),
    shipping_fee_piastres INTEGER NOT NULL CHECK(typeof(shipping_fee_piastres) = 'integer') CHECK(shipping_fee_piastres >= 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracking_events (
    id INTEGER NOT NULL PRIMARY KEY,
    tracking_number TEXT NOT NULL REFERENCES shipments(tracking_number),
    occurred_at TEXT NOT NULL,
    code TEXT NOT NULL  CHECK(code IN ('CREATED','PICKED_UP','ARRIVED_HUB','DEPARTED_HUB','CUSTOMS_CLEARED','OUT_FOR_DELIVERY','DELIVERY_FAILED','DELIVERED','CUSTOMS_HOLD','RETURN_TO_SENDER','ADDRESS_CHANGED','RETURNED')),
    location TEXT NOT NULL,
    detail TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS return_cases (
    id TEXT NOT NULL PRIMARY KEY,
    tracking_number TEXT NOT NULL REFERENCES shipments(tracking_number),
    opened_at TEXT NOT NULL,
    reason TEXT NOT NULL  CHECK(reason IN ('damaged','wrong_item','not_wanted','late','other')),
    status TEXT NOT NULL  CHECK(status IN ('open','approved','refused','received')),
    decision_code TEXT NOT NULL  CHECK(decision_code IN ('NOT_DELIVERED','MERCHANT_NOT_ON_PLAN','CATEGORY_EXCLUDED','ALREADY_OPEN','WINDOW_CLOSED','ALLOWED')),
    decided_at TEXT,
    decided_by TEXT REFERENCES staff(id),
    note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT NOT NULL PRIMARY KEY,
    tracking_number TEXT NOT NULL REFERENCES shipments(tracking_number),
    kind TEXT NOT NULL  CHECK(kind IN ('damage','loss','delay')),
    opened_at TEXT NOT NULL,
    claimed_piastres INTEGER NOT NULL CHECK(typeof(claimed_piastres) = 'integer'),
    status TEXT NOT NULL  CHECK(status IN ('open','approved','refused','paid')),
    decision_code TEXT NOT NULL  CHECK(decision_code IN ('INVALID_AMOUNT','ALREADY_EXISTS','NOT_DELIVERED','WINDOW_CLOSED','ELIGIBLE','DELIVERED','NOT_LATE_ENOUGH','SERVICE_NOT_COVERED')),
    payable_piastres INTEGER NOT NULL CHECK(typeof(payable_piastres) = 'integer') CHECK(payable_piastres >= 0) CHECK(status != 'refused' OR payable_piastres = 0),
    decided_at TEXT,
    decided_by TEXT REFERENCES staff(id),
    note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS address_changes (
    id TEXT NOT NULL PRIMARY KEY,
    tracking_number TEXT NOT NULL REFERENCES shipments(tracking_number),
    requested_at TEXT NOT NULL,
    new_city TEXT NOT NULL,
    new_address_line TEXT NOT NULL,
    status TEXT NOT NULL  CHECK(status IN ('applied','refused')),
    decision_code TEXT NOT NULL  CHECK(decision_code IN ('TOO_LATE','CUSTOMS_HOLD','ALREADY_CHANGED','DIFFERENT_CITY','ALLOWED')),
    decided_by TEXT NOT NULL REFERENCES staff(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT NOT NULL PRIMARY KEY,
    received_at TEXT NOT NULL,
    channel TEXT NOT NULL  CHECK(channel IN ('email','web_form','chat')),
    from_name TEXT NOT NULL,
    from_email TEXT NOT NULL,
    customer_id TEXT REFERENCES customers(id),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL  CHECK(status IN ('new','answered','closed')),
    assigned_to TEXT REFERENCES staff(id),
    origin TEXT NOT NULL  CHECK(origin IN ('generated','authored'))
);

CREATE TABLE IF NOT EXISTS message_labels (
    message_id TEXT NOT NULL PRIMARY KEY REFERENCES messages(id),
    primary_topic TEXT NOT NULL  CHECK(primary_topic IN ('status_question','delay','return','damage','address_change','claim_followup','billing','other')),
    topics TEXT NOT NULL CHECK(json_valid(topics) AND json_type(topics) = 'array'),
    tracking_numbers TEXT NOT NULL CHECK(json_valid(tracking_numbers) AND json_type(tracking_numbers) = 'array'),
    invalid_tracking_mentions TEXT NOT NULL CHECK(json_valid(invalid_tracking_mentions) AND json_type(invalid_tracking_mentions) = 'array'),
    missing TEXT NOT NULL CHECK(json_valid(missing) AND json_type(missing) = 'array'),
    contains_instructions INTEGER NOT NULL CHECK(contains_instructions IN (0,1)),
    escalation TEXT NOT NULL  CHECK(escalation IN ('none','legal_threat','abusive','safety')),
    labelled_by TEXT NOT NULL REFERENCES staff(id)
);

CREATE TABLE IF NOT EXISTS replies (
    id TEXT NOT NULL PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(id),
    sent_at TEXT NOT NULL,
    author TEXT NOT NULL REFERENCES staff(id),
    body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT NOT NULL PRIMARY KEY,
    kind TEXT NOT NULL  CHECK(kind IN ('waybill','commercial_invoice')),
    tracking_number TEXT NOT NULL REFERENCES shipments(tracking_number),
    issued_at TEXT NOT NULL,
    layout TEXT NOT NULL  CHECK(layout IN ('a','b','c')),
    body TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS events_shipment_time ON tracking_events(tracking_number, occurred_at, id);
CREATE INDEX IF NOT EXISTS messages_time ON messages(received_at, id);
