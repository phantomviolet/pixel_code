#include <Arduino.h>
#include <ESP32Servo.h>

// ============ 설정 값 ============
#define HALL_PIN 14
#define SERVO_PIN 13
#define WHEEL_DIAMETER 0.2
#define MAGNET_COUNT 1

// ============ 상태별 서보 각도 ============
const int SAFE_ANGLE = 60;         // 정상 주행 상태
const int WARNING_ANGLE = 90;      // 경고 상태
const int DECELERATE_ANGLE = 120;  // 감속 상태

// ============ 위험 단계 ============
enum State {
  SAFE,
  WARNING,
  DECELERATE
};

State currentState = SAFE;
int ttc_sustained_count = 0;

// ============ 서보 ============
Servo myservo;

// ============ 홀센서 속도 측정 ============
volatile unsigned int pulseCount = 0;
unsigned long lastSpeedCheckTime = 0;
float currentSpeed = 0.0;

void IRAM_ATTR onHallPulse() {
  pulseCount++;
}

float readSpeed() {
  unsigned long now = millis();
  unsigned long delta = now - lastSpeedCheckTime;

  if (delta >= 200) {
    noInterrupts();
    unsigned int count = pulseCount;
    pulseCount = 0;
    interrupts();

    float wheelCircumference = WHEEL_DIAMETER * 3.1416;
    float rps = (float)count / MAGNET_COUNT / ((float)delta / 1000.0);
    currentSpeed = rps * wheelCircumference;
    lastSpeedCheckTime = now;
  }

  return currentSpeed;
}

// ============ 라이다 ============
float readLidar() {
  if (Serial2.available() >= 9) {
    if (Serial2.read() == 0x59 && Serial2.peek() == 0x59) {
      Serial2.read(); // 두 번째 0x59

      uint8_t dist_L = Serial2.read();
      uint8_t dist_H = Serial2.read();
      uint16_t distance_cm = (dist_H << 8) | dist_L;

      for (int i = 0; i < 5; i++) Serial2.read(); // 나머지 바이트 버림

      return distance_cm / 100.0;
    } else {
      Serial2.read(); // 헤더 불일치 시 버림
    }
  }

  return -1.0; // 센서 오류
}

// ============ TTC 계산 ============
float getTTC(float distance, float speed) {
  if (speed <= 0.0) return INFINITY;
  return distance / speed;
}

// ============ 상태 업데이트 ============
void updateState(float distance, float speed, float ttc) {
  if (speed < 0.5) {
    currentState = SAFE;
    ttc_sustained_count = 0;
    return;
  }

  if (ttc < 1.2) ttc_sustained_count++;
  else ttc_sustained_count = 0;

  if ((ttc < 1.2 && ttc_sustained_count >= 2) || distance < 1.5) {
    currentState = DECELERATE;
  } else if (ttc < 2.0) {
    currentState = WARNING;
  } else {
    currentState = SAFE;
  }
}

// ============ 서보 제어 ============
void applyServoAngle(int angle) {
  myservo.write(angle);
  Serial.print("서보 회전각 설정: ");
  Serial.println(angle);
}

void triggerWarning() {
  Serial.println("WARNING");
  applyServoAngle(WARNING_ANGLE); // 예: 중간
}

void initiateDeceleration() {
  Serial.println("DECELERATE");
  applyServoAngle(DECELERATE_ANGLE); // 예: 감속용
}

void stopWarning() {
  // LED OFF, 진동 OFF 등
}

void stopDeceleration() {
  Serial.println("✅ SAFE");
  applyServoAngle(SAFE_ANGLE); // 예: 정상 주행
}

// ============ main loop ============
void loop() {
  float distance = readLidar();
  float speed = readSpeed();
  float ttc = getTTC(distance, speed);

  Serial.print("거리: "); Serial.print(distance); Serial.print(" m, ");
  Serial.print("속도: "); Serial.print(speed); Serial.print(" m/s, ");
  Serial.print("TTC: "); Serial.println(ttc);

  updateState(distance, speed, ttc);

  switch (currentState) {
    case SAFE:
      stopWarning();
      stopDeceleration();
      break;
    case WARNING:
      triggerWarning();
      stopDeceleration();
      break;
    case DECELERATE:
      triggerWarning();
      initiateDeceleration();
      break;
  }

  delay(30);
}

// ============ 초기화 ============
void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, 16, 17); // 라이다 연결
  pinMode(HALL_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(HALL_PIN), onHallPulse, FALLING);

  myservo.setPeriodHertz(50);
  myservo.attach(SERVO_PIN, 500, 2400); // 500~2400μs = 0~180도 범위
  myservo.write(90); // 초기값
}