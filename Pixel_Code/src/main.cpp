#include <Arduino.h>
#include <ESP32Servo.h>

// 핀 설정
#define SERVO_PIN 32
#define LIDAR_RX 16
#define LIDAR_TX 17
#define HALL_PIN 26

// 바퀴 및 자석 설정
#define WHEEL_DIAMETER 0.112     // 단위: m
#define MAGNET_COUNT 1

// TTC 임계값 (초)
const float TTC_DECELERATE = 1.2;
const float TTC_WARNING = 2.0;

// 서보 각도
const int SAFE_ANGLE = 350;
const int WARNING_ANGLE = 150;
const int DECELERATE_ANGLE = 0;

// 루프 주기 제어
const unsigned long LOOP_INTERVAL_MS = 30;
unsigned long lastLoopTime = 0;

// 상태 정의
enum State {
  SAFE,
  WARNING,
  DECELERATE
};

State currentState = SAFE;
State lastState = SAFE;

Servo myservo;

// 홀센서 측정 관련 변수
volatile unsigned int pulseCount = 0;
unsigned long lastSpeedCheckTime = 0;
float currentSpeed = 0.0;

void IRAM_ATTR onHallPulse() {
  pulseCount++;
}

int dangerCount = 0;
const int dangerThreshold = 3;

void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, LIDAR_RX, LIDAR_TX);

  // 서보 초기화
  myservo.setPeriodHertz(50);
  myservo.attach(SERVO_PIN, 500, 2400);
  myservo.write(310);
  myservo.write(SAFE_ANGLE);

  // 홀센서 설정
  pinMode(HALL_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(HALL_PIN), onHallPulse, FALLING);
  lastSpeedCheckTime = millis();
}

void loop() {
  // 속도 계산 (200ms마다)
  unsigned long now = millis();
  if (now - lastSpeedCheckTime >= 200) {
    noInterrupts();
    unsigned int count = pulseCount;
    pulseCount = 0;
    interrupts();

    float wheelCircumference = WHEEL_DIAMETER * 3.1416;
    float rps = (float)count / MAGNET_COUNT / ((float)(now - lastSpeedCheckTime) / 1000.0);
    currentSpeed = rps * wheelCircumference;

    lastSpeedCheckTime = now;

    Serial.print("속도: ");
    Serial.print(currentSpeed);
    Serial.println(" m/s");
  }

  // 라이다 거리 측정
  int distance = -1;
  if (Serial2.available() >= 9) {
    if (Serial2.read() == 0x59 && Serial2.peek() == 0x59) {
      Serial2.read();  // 두 번째 0x59
      uint8_t dist_L = Serial2.read();
      uint8_t dist_H = Serial2.read();
      distance = (dist_H << 8) | dist_L;

      Serial2.read();  // strength L
      Serial2.read();  // strength H
      Serial2.read();  // reserved
      Serial2.read();  // signal quality
      Serial2.read();  // checksum

    } else {
      Serial2.read();  // 잘못된 데이터 버림
    }
  }

  // TTC 계산 및 상태 판별
  if (distance > 0 && currentSpeed > 0.01) {
    float ttc = (distance / 100.0) / currentSpeed;

    if (ttc < TTC_DECELERATE || distance < 150) {
      currentState = DECELERATE;
    } else if (ttc < TTC_WARNING) {
      currentState = WARNING;
    } else {
      currentState = SAFE;
    }

    // dangerCount 누적
    if (currentState == WARNING || currentState == DECELERATE) {
      dangerCount++;
    } else {
      dangerCount = 0;
    }

    // 일정 횟수 이상 누적되면 상태 반영 및 서보 작동
    if (dangerCount >= dangerThreshold && currentState != lastState) {
      lastState = currentState;

      switch (currentState) {
        case WARNING:
          myservo.write(WARNING_ANGLE);
          Serial.println("WAR");
          break;
        case DECELERATE:
          myservo.write(DECELERATE_ANGLE);
          Serial.println("DEC");
          break;
        default:
          break;
      }

      delay(2500);
      myservo.write(SAFE_ANGLE);
      Serial.println("SAFE (복귀)");
      dangerCount = 0;
    }
  }
}