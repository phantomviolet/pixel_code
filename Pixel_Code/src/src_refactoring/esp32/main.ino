#include <Arduino.h>
#include <ESP32Servo.h>

// ===== 핀/서보 설정 (변경 없음) =====
const int SERVO_PIN = 26;
const int HALL_PIN  = 25;
const int SERVO_MIN_US = 500;
const int SERVO_MAX_US = 2500;
const int SERVO_SAFE_US  = 2500;
const int SERVO_WARN_US  = 2000;
const int SERVO_BRAKE_US = 1500;

Servo servo;
int  current_deg = 0;
int  target_us   = SERVO_SAFE_US;

// ===== 바퀴/홀센서 파라미터 (변경 없음) =====
const float wheel_circum_m = 0.408f;
const int   pulses_per_rev = 1;

// ===== 속도 산출 파라미터 =====
// STAT/하트비트 주기(기존 유지)
const unsigned long SPEED_INTERVAL_MS = 50;
// ★ 날것 계산용: 1초 창으로 단순 펄스 카운트 기반 속도 산출
const unsigned long SPEED_WINDOW_MS   = 1000;

// ===== 속도 상태값 =====
volatile unsigned long pulseCount = 0;  // ISR에서 증가
unsigned long last_speed_calc_ms = 0;   // 1초 창 타이밍
float rpm   = 0.0f;                     // sendSTAT에서 사용(유지)
float v_mps = 0.0f;                     // sendSTAT에서 사용(유지)

// ===== STAT/CLI (변경 없음) =====
bool quiet = false;
unsigned long last_stat_ms = 0;
unsigned long hb = 0;
int err_code = 0;
String rxbuf;

// ===== 유틸 (변경 없음) =====
static int deg_to_us(int deg) {
  if (deg <= 0)   return SERVO_SAFE_US;
  if (deg >= 140) return SERVO_BRAKE_US;
  if (deg <= 100) {
    float t = (float)deg / 100.0f;
    return (int)round((1.0f - t) * SERVO_SAFE_US + t * SERVO_WARN_US);
  } else {
    float t = (float)(deg - 100) / 40.0f;
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

// ===== ISR (★ 날것: 펄스 카운트만) =====
void IRAM_ATTR onHallPulse() {
  pulseCount++;   // 필터/디바운스/타임아웃 없음
}

// ===== CLI (변경 없음) =====
void handleCommand(String line) {
  line.trim();
  if (!line.length()) return;
  int sp = line.indexOf(' ');
  String cmd = (sp < 0) ? line : line.substring(0, sp);
  String arg = (sp < 0) ? ""   : line.substring(sp + 1);
  cmd.toUpperCase();
  if (cmd == "PING") { Serial.println("PONG"); }
  else if (cmd == "GET_STAT") { sendSTAT(); }
  else if (cmd == "SET_DEG") { int deg = arg.toInt(); setServoDeg(deg); Serial.printf("OK angle=%d us=%d\n", current_deg, target_us); }
  else if (cmd == "SET_US") { int us = arg.toInt(); us = constrain(us, SERVO_MIN_US, SERVO_MAX_US); servo.writeMicroseconds(us); target_us = us; Serial.printf("OK us=%d\n", us); }
  else if (cmd == "QUIET") { quiet = (arg.toInt() != 0); Serial.printf("OK quiet=%d\n", (int)quiet); }
  else { Serial.println("ERR code=9 msg=unknown_cmd"); }
}

// ===== setup (변경 없음) =====
void setup() {
  Serial.begin(115200);
  delay(100);
  servo.attach(SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US);
  setServoDeg(0);

  pinMode(HALL_PIN, INPUT_PULLUP);  // 기존 유지
  attachInterrupt(digitalPinToInterrupt(HALL_PIN), onHallPulse, FALLING); // 기존 유지

  unsigned long now = millis();
  last_speed_calc_ms = now;
  last_stat_ms  = now;
  Serial.println("ready");
}

// ===== loop (★ 속도 측정만 날것으로 교체, 그 외 불변) =====
void loop() {
  unsigned long now = millis();

  // --- Serial RX (논블로킹, 그대로) ---
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxbuf.length()) { handleCommand(rxbuf); rxbuf = ""; }
    } else {
      rxbuf += c;
      if (rxbuf.length() > 128) rxbuf.remove(0, rxbuf.length() - 128);
    }
  }

  // --- ★ 날것 속도 계산: 1초 창으로 펄스→속도 ---
  if (now - last_speed_calc_ms >= SPEED_WINDOW_MS) {
    unsigned long count;
    noInterrupts();
    count = pulseCount;     // 지난 1초 동안의 펄스 수
    pulseCount = 0;         // 창 이동: 카운터 리셋
    interrupts();

    // 회전수, 이동거리
    float window_s = (float)SPEED_WINDOW_MS / 1000.0f;
    float rev      = (pulses_per_rev > 0) ? (float)count / (float)pulses_per_rev : 0.0f;
    float dist_m   = rev * wheel_circum_m;

    // 속도(m/s), RPM
    v_mps = (window_s > 0.0f) ? (dist_m / window_s) : 0.0f;
    float rps = (window_s > 0.0f) ? (rev / window_s) : 0.0f;
    rpm = rps * 60.0f;

    last_speed_calc_ms = now;
  }

  // --- STAT 주기 송신(quiet=0일 때만, 그대로) ---
  if (!quiet && (now - last_stat_ms >= SPEED_INTERVAL_MS)) {
    hb++;
    sendSTAT();
    last_stat_ms = now;
  }

  delay(1);
}