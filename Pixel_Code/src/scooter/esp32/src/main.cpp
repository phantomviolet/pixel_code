#include <Arduino.h>
#include "motor_control.h"

// ===== 상태/파라미터 =====
enum Mode { MODE_NORMAL, MODE_CORNER };
static Mode currentMode = MODE_NORMAL;

static uint32_t lastHbMs = 0;
static bool hbArmed = false;                         // 첫 HB 수신 전에는 타임아웃 비활성
static const uint32_t HEARTBEAT_TIMEOUT_MS = 1500;   // 필요시 조정

static int speedCapKmh = 0; // CORNER 속도 상한 (RPi가 SPD_CAP로 세팅)

// ===== 센서 입력 (TFmini/Hall 도착 전 임시 스텁) =====
static float   simSpeedKmh = 0.0f;   // DBG_SPEED로 변경
static uint16_t simDistMm  = 9999;   // DBG_DIST 로 변경

// 실제 센서 붙이면 이 함수들만 교체하면 됨
static float readSpeedKmh()  { return simSpeedKmh; }
static uint16_t readDistMm() { return simDistMm; }

// ===== 브레이크 래치/히스테리시스 =====
static bool brakeLatched = false;     // 브레이크 상태 유지 래치
static uint8_t dangerCount = 0;       // 연속 프레임 확증용
static uint8_t safeCount   = 0;

static const uint8_t DANGER_NEED = 2; // 위험 확증 프레임 수
static const uint8_t SAFE_NEED   = 2; // 해제 확증 프레임 수

// ===== 유틸 =====
static void sendAck(const char* what, const String& arg="") {
  if (arg.length()) Serial.printf("ACK %s %s\n", what, arg.c_str());
  else              Serial.printf("ACK %s\n", what);
}

static void emergencyBrake() {
  mc_set_brake_brake();
  Serial.println("EVENT BRAKE");
}

static void applyCmd(const String& c) {
  // NORMAL 모드에서만 의미 있게 사용 (CORNER는 ESP32 전권)
  if (c == "SAFE")      mc_set_brake_safe();
  else if (c == "SLOW") mc_set_brake_slow();
  else if (c == "BRAKE")mc_set_brake_brake();
}

// ===== 프로토콜 파서 =====
// MODE NORMAL|CORNER
// CMD SAFE|SLOW|BRAKE
// SPD_CAP <kmh>
// HB
// (디버그) DBG_DIST <mm>, DBG_SPEED <kmh>
static void parseLine(const String& line) {
  if (line.startsWith("MODE ")) {
    String m = line.substring(5); m.trim();
    if (m == "NORMAL")  { currentMode = MODE_NORMAL;  sendAck("MODE","NORMAL"); }
    if (m == "CORNER")  { currentMode = MODE_CORNER;  sendAck("MODE","CORNER"); brakeLatched=false; dangerCount=0; safeCount=0; }
  } else if (line.startsWith("CMD ")) {
    String c = line.substring(4); c.trim();
    applyCmd(c);
    sendAck("CMD", c);
  } else if (line.startsWith("SPD_CAP ")) {
    speedCapKmh = line.substring(8).toInt();
    sendAck("SPD_CAP", String(speedCapKmh));
  } else if (line == "HB") {
    lastHbMs = millis();
    hbArmed  = true;
    sendAck("HB");
  } else if (line.startsWith("DBG_DIST ")) {               // 테스트용
    simDistMm = (uint16_t) line.substring(9).toInt();
    sendAck("DBG_DIST", String(simDistMm));
  } else if (line.startsWith("DBG_SPEED ")) {              // 테스트용
    simSpeedKmh = line.substring(10).toFloat();
    sendAck("DBG_SPEED", String(simSpeedKmh,1));
  }
}

// ===== 초기화 =====
void setup() {
  Serial.begin(115200);
  delay(100);

  // 서보 초기화 (GPIO 5 사용 예시. 실제 배선에 맞춰 수정 가능)
  mc_init(5);

  lastHbMs = millis();
  Serial.println("ESP32 ready");
}

// ===== 메인 루프 =====
void loop() {
  // 1) 시리얼 라인 파싱
  static String buf;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      buf.trim();
      if (buf.length()) parseLine(buf);
      buf = "";
    } else {
      buf += ch;
    }
  }

  // 2) HB 타임아웃 → fail-safe (첫 HB 오기 전에는 비활성)
  if (hbArmed && (millis() - lastHbMs > HEARTBEAT_TIMEOUT_MS)) {
    emergencyBrake();
    lastHbMs = millis();  // 스팸 방지
  }

  // 3) CORNER 모드 전권: 속도상한 + 거리임계 판단
  if (currentMode == MODE_CORNER) {
    const float    speed = readSpeedKmh();   // km/h
    const uint16_t dist  = readDistMm();     // mm

    // 3-1) 속도 상한 적용(간단형): 상한 초과 시 감속 브레이크
    if (speedCapKmh > 0 && speed > (float)speedCapKmh + 0.5f) {
      mc_set_brake_slow();
    }

    // 3-2) 동적 정지거리 임계 (튜닝 포인트)
    // d_stop(mm) = a*speed_kmh + b
    const uint16_t d_stop    = (uint16_t)(350.0f * speed + 1500.0f);  // 예: 10km/h → 5000mm
    const uint16_t d_release = d_stop + 800;                          // 히스테리시스

    // 연속 프레임 확증
    if (dist <= d_stop)  { dangerCount = min<uint8_t>(255, dangerCount+1); safeCount=0; }
    else if (dist > d_release) { safeCount = min<uint8_t>(255, safeCount+1); dangerCount=0; }
    else { /* 중간 영역: 카운터 유지 */ }

    if (!brakeLatched && dangerCount >= DANGER_NEED) {
      mc_set_brake_brake();
      Serial.println("EVENT BRAKE");
      brakeLatched = true;
    } else if (brakeLatched && safeCount >= SAFE_NEED) {
      mc_set_brake_slow();              // 완전 해제 대신 완만히 해제
      brakeLatched = false;
    }
  }

  // 4) 주기 텔레메트리(1Hz 예시)
  static uint32_t t = 0;
  if (millis() - t > 1000) {
    t = millis();
    Serial.printf("SPEED %.1f\n", readSpeedKmh());
    Serial.printf("DIST %u\n", readDistMm());
  }
}