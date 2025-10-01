#include "motor_control.h"
#include <Servo.h>

static Servo brake;
static int s_safe = 90;    // 각도 튜닝 포인트
static int s_slow = 120;
static int s_brake = 150;

void mc_init(int servoPin) {
  brake.attach(servoPin, 500, 2500); // 50Hz, 펄스 폭 범위
  delay(100);
  brake.write(s_safe);
}

void mc_set_brake_safe()  { brake.write(s_safe); }
void mc_set_brake_slow()  { brake.write(s_slow); }
void mc_set_brake_brake() { brake.write(s_brake); }