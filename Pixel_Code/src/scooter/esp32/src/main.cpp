/*******************************************************
 * ESP32 통합 펌웨어 (MG996R + 홀센서 + 직렬 프로토콜)
 * - 프로토콜(라즈베리파이 → ESP32):  "A:<angle>\n"
 *   예) A:300  → 내부에서 150°로 스케일링(360 입력 대비 1/2)
 * - 상태 전송(ESP32 → 라즈베리파이): "V:<kmh>\n" 주기적으로 송신
 * - 유틸: "GET MAP", "SPEED?", "PULSES?", "RESET", "PING"
 *******************************************************/
#include <Arduino.h>
#include <ESP32Servo.h>

/* ===== 핀/하드웨어 설정 ===== */
#define SERVO_PIN   25     // MG996R 신호핀 (25/26/27/32/33 권장)
#define HALL_PIN    26     // 홀센서 입력핀 (내부 풀업 사용; 외부 풀업이면 INPUT으로)

// 바퀴/자석 파라미터 (프로젝트 값에 맞게 조정)
static const float WHEEL_DIAMETER_M = 0.112f;  // 112mm
static const uint8_t MAGNET_COUNT   = 1;       // 회전당 자석 1개

/* ===== 서보(MG996R) 설정 ===== */
static const int SERVO_MIN_US = 1000;   // 보수적 시작 범위 (필요시 800~2200으로 확장)
static const int SERVO_MAX_US = 2000;
static const int DEG_MIN = 0;
static const int DEG_MAX = 180;
static const uint16_t SERVO_HZ = 50;    // 50 Hz

// 부드러운 이동(램프): 급전류 피크 억제
static const uint8_t  RAMP_STEP_DEG   = 3;   // 한 번에 이동하는 각도
static const uint16_t RAMP_INTERVAL_MS= 8;   // 스텝 간 간격(ms)

/* ===== 속도/상태 주기 ===== */
static const uint16_t SPEED_WINDOW_MS = 250;   // 속도 갱신 주기
static const uint16_t STAT_INTERVAL_MS= 200;   // V:<kmh> 전송 주기

/* ===== 전역 상태 ===== */
Servo servo;

volatile uint32_t g_pulseCount = 0;   // ISR에서 증가
uint32_t lastPulseCount = 0;

uint32_t lastSpeedMs = 0;
float currentKmh = 0.0f;

uint32_t lastStatMs = 0;

int currentDeg = 90;     // 현재 출력 각도(램프 기준)
int targetDeg  = 90;     // 목표 각도
uint32_t lastRampMs = 0;

String rx;               // 시리얼 수신 버퍼

/* ===== 유틸 ===== */
static inline int clampInt(int v, int lo, int hi) {
  return (v < lo) ? lo : (v > hi) ? hi : v;
}

static inline int degToUs(int deg) {
  deg = clampInt(deg, DEG_MIN, DEG_MAX);
  return map(deg, DEG_MIN, DEG_MAX, SERVO_MIN_US, SERVO_MAX_US);
}

/* ===== 홀센서 ISR ===== */
void IRAM_ATTR onHall() {
  g_pulseCount++;
}

/* ===== 각도 설정(스케일 포함) =====
 *  - 0..180 : 그대로
 *  - 181..360 : 1/2 스케일 (예: 300 → 150)  ← esp32_comm.py의 (SAFE=300 등)과 호환
 */
void setTargetAngleFromInput(int inDeg) {
  int d = inDeg;
  if (d < 0) d = 0;
  if (d > 360) d = 360;
  if (d > 180) d = (d + 1) / 2;  // 반올림 스케일링
  targetDeg = clampInt(d, DEG_MIN, DEG_MAX);

  // ACK
  int us = degToUs(targetDeg);
  Serial.printf("OK %d %dus\n", targetDeg, us);
}

/* ===== 램프(부드러운 이동) ===== */
void rampServoIfNeeded() {
  uint32_t now = millis();
  if (now - lastRampMs < RAMP_INTERVAL_MS) return;
  lastRampMs = now;

  if (currentDeg == targetDeg) return;

  int step = (targetDeg > currentDeg) ? RAMP_STEP_DEG : -RAMP_STEP_DEG;
  int nextDeg = currentDeg + step;

  // 목표를 넘어가지 않게 캡
  if ((step > 0 && nextDeg > targetDeg) || (step < 0 && nextDeg < targetDeg)) {
    nextDeg = targetDeg;
  }

  currentDeg = clampInt(nextDeg, DEG_MIN, DEG_MAX);
  int us = degToUs(currentDeg);
  servo.writeMicroseconds(us);
}

/* ===== 속도 계산 & 전송 ===== */
void updateSpeedIfDue() {
  uint32_t now = millis();
  if (now - lastSpeedMs < SPEED_WINDOW_MS) return;
  uint32_t dt = now - lastSpeedMs;
  lastSpeedMs = now;
  if (dt == 0) return;

  uint32_t pulses = g_pulseCount;
  uint32_t dPulse = pulses - lastPulseCount;
  lastPulseCount = pulses;

  // 시간(s)
  float dt_s = dt / 1000.0f;

  // 회전수 = 펄스 / (자석 수)
  float rev = (MAGNET_COUNT > 0) ? ( (float)dPulse / (float)MAGNET_COUNT ) : 0.0f;

  // 속도(m/s) = 회전수/초 * 둘레
  float circumference = PI * WHEEL_DIAMETER_M;
  float mps = (dt_s > 0.0f) ? (rev / dt_s) * circumference : 0.0f;
  currentKmh = mps * 3.6f;
}

void sendStatIfDue() {
  uint32_t now = millis();
  if (now - lastStatMs < STAT_INTERVAL_MS) return;
  lastStatMs = now;
  Serial.printf("V:%.3f\n", currentKmh);
}

/* ===== 시리얼 명령 파서 =====
 * 지원:
 *   "A:<int>" 또는 "ANGLE:<int>"  → 목표 각도
 *   "GET MAP"                    → 맵/사양 안내
 *   "SPEED?"                     → 즉시 속도 송신
 *   "PULSES?"                    → 펄스 수 송신
 *   "RESET"                      → 펄스/속도창 리셋
 *   "PING"                       → "PONG"
 * 줄끝: CR/LF 모두 허용
 */
void handleLine(String line) {
  line.trim();
  line.toUpperCase();
  if (line.length() == 0) return;

  // A:<int> / ANGLE:<int>
  if (line.startsWith("A:") || line.startsWith("ANGLE:")) {
    int idx = line.indexOf(':');
    if (idx > 0) {
      String n = line.substring(idx + 1);
      n.trim();
      if (n.length() > 0) {
        int inDeg = n.toInt();
        setTargetAngleFromInput(inDeg);
        return;
      }
    }
    Serial.println("ERR FORMAT (A:<int>)");
    return;
  }

  if (line == "GET MAP") {
    Serial.printf("MAP SERVO=MG996R DEG=0-180 US=%d-%d SCALE_360=HALF PIN=%d\n",
                  SERVO_MIN_US, SERVO_MAX_US, SERVO_PIN);
    return;
  }

  if (line == "SPEED?") {
    Serial.printf("V:%.3f\n", currentKmh);
    return;
  }

  if (line == "PULSES?") {
    Serial.printf("P:%u\n", g_pulseCount);
    return;
  }

  if (line == "RESET") {
    noInterrupts();
    g_pulseCount = 0;
    interrupts();
    currentKmh = 0.0f;
    Serial.println("OK RESET");
    return;
  }

  if (line == "PING") {
    Serial.println("PONG");
    return;
  }

  Serial.println("ERR UNKNOWN");
}

/* ===== 시리얼 수신 루프 ===== */
void serialPoll() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') {
      if (rx.length() > 0) {
        handleLine(rx);
        rx = "";
      }
    } else {
      if (rx.length() < 64) rx += c;   // 과도한 길이 보호
    }
  }
}

/* ===== SETUP/LOOP ===== */
void setup() {
  Serial.begin(115200);

  // 홀센서
  pinMode(HALL_PIN, INPUT_PULLUP);      // 외부 풀업이면 INPUT으로 변경
  attachInterrupt(digitalPinToInterrupt(HALL_PIN), onHall, FALLING);

  // 서보
  servo.setPeriodHertz(SERVO_HZ);
  servo.attach(SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US);
  // 부팅 안전 위치
  currentDeg = targetDeg = 90;
  servo.writeMicroseconds(degToUs(currentDeg));

  // 부팅 배너
  Serial.println("READY MG996R (A:<deg>, GET MAP, SPEED?, PULSES?, RESET, PING)");
}

void loop() {
  // 1) 시리얼 명령 처리
  serialPoll();

  // 2) 속도 갱신 & 상태 송신
  updateSpeedIfDue();
  sendStatIfDue();

  // 3) 서보 부드러운 이동
  rampServoIfNeeded();
}