import pandas as pd
import matplotlib.pyplot as plt

data = pd.read_csv("result.csv")

plt.figure(figsize=(8,6))
for result, group in data.groupby('Result'):
    plt.scatter(group['Distance(m)'], group['Speed(m/s)'], label=result, alpha=0.7)

plt.xlabel('Distance (m)')
plt.ylabel('Speed (m/s)')
plt.title('Reult - 3.0(m/s^2)')
plt.legend()
plt.grid(True)
plt.show()