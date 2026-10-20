
-- =====================================================
-- FlotIQ | ESQUEMA DE BASE DE DATOS
-- Fase 2: PostgreSQL / Supabase
-- =====================================================


-- 1. VEHÍCULOS
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id VARCHAR(10) PRIMARY KEY,
    manufacturer VARCHAR(50),
    model VARCHAR(100),
    version VARCHAR(100),
    model_year INTEGER,
    battery_usable_kwh NUMERIC(6,2),
    max_ac_charging_kw NUMERIC(6,2),
    wltp_consumption_kwh_100km NUMERIC(6,2),
    simulated_consumption_kwh_100km NUMERIC(6,2),
    data_type VARCHAR(20) NOT NULL DEFAULT 'synthetic'
);


-- 2. CONDUCTORES
CREATE TABLE IF NOT EXISTS drivers (
    driver_id VARCHAR(10) PRIMARY KEY,
    first_name VARCHAR(100),
    last_name_1 VARCHAR(100),
    last_name_2 VARCHAR(100),
    full_name VARCHAR(300),
    contract_type VARCHAR(50),
    weekly_hours INTEGER,
    preferred_shift VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    data_type VARCHAR(20) NOT NULL DEFAULT 'synthetic'
);

-- 3. TURNOS
CREATE TABLE IF NOT EXISTS shifts (
    shift_id VARCHAR(10) PRIMARY KEY,
    driver_id VARCHAR(10) NOT NULL
        REFERENCES drivers(driver_id),
    shift_date DATE NOT NULL,
    shift_type VARCHAR(20) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    planned_hours NUMERIC(5,2),
    data_type VARCHAR(20) NOT NULL DEFAULT 'synthetic',

    CONSTRAINT valid_shift_times
        CHECK (end_time > start_time)
);

-- 4. ASIGNACIONES
CREATE TABLE IF NOT EXISTS assignments (
    assignment_id VARCHAR(10) PRIMARY KEY,
    shift_id VARCHAR(10) NOT NULL UNIQUE
        REFERENCES shifts(shift_id),
    vehicle_id VARCHAR(10) NOT NULL
        REFERENCES vehicles(vehicle_id),
    data_type VARCHAR(20) NOT NULL DEFAULT 'synthetic'
);

-- 5. TRAYECTOS
CREATE TABLE IF NOT EXISTS trips (
    trip_id VARCHAR(10) PRIMARY KEY,
    assignment_id VARCHAR(10) NOT NULL
        REFERENCES assignments(assignment_id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    origin_area VARCHAR(100),
    destination_area VARCHAR(100),
    distance_km NUMERIC(8,2),
    duration_minutes INTEGER,
    average_speed_kmh NUMERIC(6,2),
    energy_consumed_kwh NUMERIC(8,3),
    data_type VARCHAR(20) NOT NULL DEFAULT 'synthetic',

    CONSTRAINT valid_trip_times
        CHECK (end_time > start_time),

    CONSTRAINT valid_trip_distance
        CHECK (distance_km >= 0),

    CONSTRAINT valid_trip_energy
        CHECK (energy_consumed_kwh >= 0)
);

-- ÍNDICES PARA CONSULTAS FRECUENTES
CREATE INDEX IF NOT EXISTS idx_shifts_driver
    ON shifts(driver_id);

CREATE INDEX IF NOT EXISTS idx_assignments_vehicle
    ON assignments(vehicle_id);

CREATE INDEX IF NOT EXISTS idx_trips_assignment
    ON trips(assignment_id);

CREATE INDEX IF NOT EXISTS idx_trips_start_time
    ON trips(start_time);


-- =====================================================
-- 6. PRECIOS DE ELECTRICIDAD (OMIE)
-- =====================================================

CREATE TABLE IF NOT EXISTS electricity_prices (
    price_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    timestamp_utc TIMESTAMPTZ NOT NULL,

    market VARCHAR(30) NOT NULL DEFAULT 'OMIE',

    price_eur_mwh NUMERIC(12,4) NOT NULL,

    source VARCHAR(100) NOT NULL DEFAULT 'OMIE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT electricity_prices_unique
        UNIQUE (timestamp_utc, market)
);

CREATE INDEX IF NOT EXISTS idx_electricity_prices_timestamp
    ON electricity_prices(timestamp_utc);

ALTER TABLE electricity_prices
    ENABLE ROW LEVEL SECURITY;


-- =====================================================
-- 7. TRÁFICO HISTÓRICO DE MADRID
-- =====================================================

CREATE TABLE IF NOT EXISTS traffic_hourly (
    traffic_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    hour TIMESTAMP NOT NULL,

    tipo_elem VARCHAR(10) NOT NULL,

    mean_intensity DOUBLE PRECISION,

    mean_speed DOUBLE PRECISION,

    intensity_count INTEGER NOT NULL,

    speed_count INTEGER NOT NULL,

    day_of_week INTEGER NOT NULL,

    hour_of_day INTEGER NOT NULL,

    is_weekend BOOLEAN NOT NULL,

    CONSTRAINT traffic_hourly_unique
        UNIQUE (hour, tipo_elem),

    CONSTRAINT valid_traffic_hour
        CHECK (hour_of_day BETWEEN 0 AND 23),

    CONSTRAINT valid_traffic_weekday
        CHECK (day_of_week BETWEEN 0 AND 6),

    CONSTRAINT valid_traffic_counts
        CHECK (
            intensity_count >= 0
            AND speed_count >= 0
        )
);

CREATE INDEX IF NOT EXISTS idx_traffic_hour
    ON traffic_hourly(hour);

ALTER TABLE traffic_hourly
    ENABLE ROW LEVEL SECURITY;


-- =====================================================
-- 8. METEOROLOGÍA HISTÓRICA DE MADRID
-- =====================================================

CREATE TABLE IF NOT EXISTS weather_hourly (
    weather_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    datetime TIMESTAMP NOT NULL UNIQUE,

    temperature_c DOUBLE PRECISION,

    precipitation_mm DOUBLE PRECISION,

    wind_speed_kmh DOUBLE PRECISION,

    CONSTRAINT valid_precipitation
        CHECK (precipitation_mm >= 0),

    CONSTRAINT valid_wind_speed
        CHECK (wind_speed_kmh >= 0)
);

CREATE INDEX IF NOT EXISTS idx_weather_datetime
    ON weather_hourly(datetime);

ALTER TABLE weather_hourly
    ENABLE ROW LEVEL SECURITY;
