#include <Arduino.h>
#include <ESP32Servo.h>

// ===== 핀/서보 설정 =====
const int SERVO_PIN = 26;     // PWM 출력 핀
const int HALL_PIN  = 25;     // 홀 센서 핀

// 서보 PWM 범위 및 현실 매핑(측정 기반)
const int SERVO_MIN_US = 500;
const int SERVO_MAX_US = 2500;

const int SERVO_SAFE_US  = 2500;  // SAFE(브레이크 해제)
const int SERVO_WARN_US  = 2000;  // WARN/CORNER(약한 감속)
const int SERVO_BRAKE_US = 1500;  // BRAKE(강한 감속)

Servo servo;
int  current_deg = 0;
int  target_us   = SERVO_SAFE_US;

// ===== 바퀴/홀센서 파라미터 =====
const float wheel_circum_m = 0.408f;  // 실둘레
const int   pulses_per_rev = 2;       // 1회전당 펄스 수

// ===== 속도 산출 파라미터 =====
const unsigned long SPEED_INTERVAL_MS = 100;   // 속도계산 주기
const unsigned long STALE_MS          = 2000;  // 이 시간 이상 무펄스면 정지 간주
const unsigned long MIN_DT_US         = 40000; // 바운스 무시 하한(µs)
const float ALPHA = 0.30f;                      // EMA 가중치

// ===== 속도 상태값 =====
volatile unsigned long last_pulse_us = 0;   // 마지막 펄스 시각(us)
volatile unsigned long period_us     = 0;   // 최근 유효 주기(us)
unsigned long last_speed_ms = 0;
float rpm   = 0.0f;
float v_mps = 0.0f;

// ===== STAT/CLI =====
bool quiet = false;                 // quiet=1이면 주기 STAT 비활성(폴링 전용)
unsigned long last_stat_ms = 0;
unsigned long hb = 0;
int err_code = 0;
const unsigned long STAT_IV_MS = 100;  // quiet=0일 때만 사용

String rxbuf;

// ===== 유틸 =====
// 각도(0/100/140) → µs (선형 보간)
static int deg_to_us(int deg) {
  if (deg <= 0)   return SERVO_SAFE_US;   // 0°
  if (deg >= 140) return SERVO_BRAKE_US;  // 140°
  if (deg <= 100) {
    float t = (float)deg / 100.0f;        // 0..100° : 2500 → 2000
    return (int)round((1.0f - t) * SERVO_SAFE_US + t * SERVO_WARN_US);
  } else {
    float t = (float)(deg - 100) / 40.0f; // 100..140°: 2000 → 1500
    return (int)round((1.0f - t) * SERVO_WARN_US + t * SERVO_BRAKE_US);
  }
}

void setServoDeg(int deg) {
  deg = constrain(deg, 0, 160);
  current_deg = deg;
  int us = deg_to_us(deg);
  us = constrain(us, SERVO_MIN_US, SERVO_MAX_US);
  servo.writeMicroseconds(us);
  target_us = us;
}

void sendSTAT() {
  unsigned long t = millis();
  Serial.printf("STAT hb=%lu angle=%d us=%d t=%lu err=%d rpm=%.2f v=%.2f\n",
                hb, current_deg, target_us, t, err_code, rpm, v_mps);
}

// ===== ISR: 주기 측정 + 디바운스(마이크로초) =====
void IRAM_ATTR onHallPulse() {
  unsigned long now_us = micros();
  unsigned long dt = now_us - last_pulse_us;
  if (last_pulse_us != 0 && dt >= MIN_DT_US) {
    period_us = dt;                 // 유효 주기 갱신
  }
  last_pulse_us = now_us;           // 마지막 펄스 시각 갱신
}

// ===== CLI =====
void handleCommand(String line) {
  line.trim();
  if (!line.length()) return;

  int sp = line.indexOf(' ');
  String cmd = (sp < 0) ? line : line.substring(0, sp);
  String arg = (sp < 0) ? ""   : line.substring(sp + 1);
  cmd.toUpperCase();

  if (cmd == "PING") {
    Serial.println("PONG");
  } else if (cmd == "GET_STAT") {
    sendSTAT();                     // 즉시 캐시 응답
  } else if (cmd == "SET_DEG") {
    int deg = arg.toInt();
    setServoDeg(deg);
    Serial.printf("OK angle=%d us=%d\n", current_deg, target_us);
  } else if (cmd == "SET_US") {     // ★ 추가: PWM µs 직접 설정
    int us = arg.toInt();
    us = constrain(us, SERVO_MIN_US, SERVO_MAX_US);
    servo.writeMicroseconds(us);
    target_us = us;
    Serial.printf("OK us=%d\n", us);
  } else if (cmd == "QUIET") {
    quiet = (arg.toInt() != 0);
    Serial.printf("OK quiet=%d\n", (int)quiet);
  } else {
    Serial.println("ERR code=9 msg=unknown_cmd");
  }
}

// ===== setup/loop =====
void setup() {
  Serial.begin(115200);
  delay(100);

  servo.attach(SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US);
  setServoDeg(0);                   // SAFE로 시작(2500us)

  pinMode(HALL_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(HALL_PIN), onHallPulse, FALLING);

  unsigned long now = millis();
  last_speed_ms = now;
  last_stat_ms  = now;

  Serial.println("ready");
}

void loop() {
  unsigned long now = millis();

  // --- Serial RX (논블로킹) ---
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxbuf.length()) { handleCommand(rxbuf); rxbuf = ""; }
    } else {
      rxbuf += c;
      if (rxbuf.length() > 128) rxbuf.remove(0, rxbuf.length() - 128);
    }
  }

  // --- 속도 계산 (경과시간 기반 추정, 100ms마다 갱신) ---
  if (now - last_speed_ms >= SPEED_INTERVAL_MS) {
    unsigned long lp_us, per_us;
    noInterrupts();
    lp_us  = last_pulse_us;   // 마지막 펄스 시각(µs)
    per_us = period_us;       // 최근 유효 주기(µs)
    interrupts();

    float rpm_inst = 0.0f, v_inst = 0.0f;

    if (lp_us == 0 || (micros() - lp_us) / 1000UL > STALE_MS) {
      // 오랜 시간 무펄스 → 정지
      rpm_inst = 0.0f; v_inst = 0.0f;
    } else {
      // 최근 펄스 이후 경과시간으로 현재 주기 추정
      unsigned long elapsed_us = micros() - lp_us;
      unsigned long eff_us = (per_us > 0) ? per_us : elapsed_us;
      if (eff_us < MIN_DT_US)     eff_us = MIN_DT_US;     // 하한
      if (eff_us > 1000000UL)     eff_us = 1000000UL;     // 상한 1s

      // 1회전 시간 T = 주기 * PPR, rps = 1/T
      float T = (eff_us / 1e6f) * (float)max(1, pulses_per_rev);
      float rps = (T > 0.0f) ? (1.0f / T) : 0.0f;

      rpm_inst = rps * 60.0f;
      v_inst   = rps * wheel_circum_m;  // m/s
    }

    // EMA로 완만하게
    rpm   = ALPHA * rpm_inst + (1.0f - ALPHA) * rpm;
    v_mps = ALPHA * v_inst   + (1.0f - ALPHA) * v_mps;

    last_speed_ms = now;
  }

  // --- STAT 주기 송신(quiet=0일 때만) ---
  if (!quiet && (now - last_stat_ms >= STAT_IV_MS)) {
    hb++;
    sendSTAT();
    last_stat_ms = now;
  }

  delay(1);
}