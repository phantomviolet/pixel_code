#include <Arduino.h>

//위험 수준을 3단계로 정의
enum State {
  SAFE,
  WARNING,
  DECELERATE
};

State currentState = SAFE;

int ttc_sustained_count = 0;

//라이다
float readLidar() {
  //실제 센서 값 읽기 추가
  uint16_t distance_cm = 100; 
  return distance_cm / 100.0;
}

//홀센서
float readSpeed() {
  //홀센서로 바퀴 속도 읽기 추가
  uint16_t speed;
  return speed;
}

//TTC
float getTTC(float distance, float speed) {
  if (speed <= 0.0) return INFINITY;
  return distance / speed;
}

//상태 업데이트
void updateState(float distance, float speed, float ttc) {
  if (speed < 0.5) {
    currentState = SAFE;
    ttc_sustained_count = 0;
    return;
  }

//위험 상황이 연속 두번 이상 감지되면 위험 감지
  if (ttc < 1.2) {
    ttc_sustained_count++;
  }
  else {
    ttc_sustained_count = 0;
  }

  if ((ttc < 1.2 && ttc_sustained_count >= 2) || distance < 1.5) {
    currentState = DECELERATE;
  } 
  else if (ttc < 2.0) {
    currentState = WARNING;
  } 
  else {
    currentState = SAFE;
  }
}

void triggerWarning() {
  //진동 or led
  Serial.println("WARNING!");
}

void initiateDeceleration() {
  // 예: 서보모터 제어
  Serial.println("DECELERATING!");
}

void stopWarning() {
  // 예: 진동 OFF
}

void stopDeceleration() {
  // 예: 서보모터 복귀
}

//main
void loop() {
  float distance = readLidar();
  float speed = readSpeed();
  float ttc = getTTC(distance, speed);

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

  delay(20);
}

void setup() {
  Serial.begin(9600);
}