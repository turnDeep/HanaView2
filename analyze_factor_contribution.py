import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, accuracy_score

# Load the generated trades
df = pd.read_csv('unified_trades.csv')

# Filter out Open trades
df = df[df['Result'] != 'Open'].copy()

# Feature Engineering
# Create binary target: 1 for Win, 0 for Loss
df['Target'] = (df['Result'] == 'Win').astype(int)

# Select features for analysis
features = ['RS_Rating', 'AD_Rating', 'VCP_Tight', 'VCP_DryUp', 'ATR_Risk', 'Has_FVG']
X = df[features]
y = df['Target']

# Handle missing values if any
X = X.fillna(X.median())

# Train/Test Split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Scale features
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Train Random Forest
rf = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
rf.fit(X_train_scaled, y_train)

# Predict
y_pred = rf.predict(X_test_scaled)

print("--- Factor Analysis using Random Forest ---")
print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
print("\nClassification Report:")
print(classification_report(y_test, y_pred))

# Feature Importance
importances = rf.feature_importances_
feature_imp_df = pd.DataFrame({'Feature': features, 'Importance': importances}).sort_values('Importance', ascending=False)

print("\n--- Feature Importances ---")
print(feature_imp_df.to_string(index=False))

# Plot Feature Importances
plt.figure(figsize=(10, 6))
plt.barh(feature_imp_df['Feature'], feature_imp_df['Importance'], color='skyblue')
plt.xlabel('Importance')
plt.title('Factor Importance for Breakout Success')
plt.gca().invert_yaxis()
plt.tight_layout()
plt.savefig('factor_importance.png')
print("\nSaved factor importance plot to factor_importance.png")

# Detailed factor analysis
print("\n--- Detailed Factor Edge Analysis ---")
for feature in features:
    if feature in ['VCP_Tight', 'VCP_DryUp', 'Has_FVG']:
        # Boolean features
        win_rate_true = df[df[feature] == True]['Target'].mean() * 100
        win_rate_false = df[df[feature] == False]['Target'].mean() * 100
        count_true = len(df[df[feature] == True])
        count_false = len(df[df[feature] == False])

        print(f"\n{feature}:")
        print(f"  True: Win Rate = {win_rate_true:.2f}% (n={count_true})")
        print(f"  False: Win Rate = {win_rate_false:.2f}% (n={count_false})")
        print(f"  Edge: {win_rate_true - win_rate_false:+.2f}%")
    else:
        # Continuous features
        median_val = df[feature].median()
        win_rate_high = df[df[feature] >= median_val]['Target'].mean() * 100
        win_rate_low = df[df[feature] < median_val]['Target'].mean() * 100
        count_high = len(df[df[feature] >= median_val])
        count_low = len(df[df[feature] < median_val])

        print(f"\n{feature}:")
        print(f"  High (>= {median_val:.2f}): Win Rate = {win_rate_high:.2f}% (n={count_high})")
        print(f"  Low (< {median_val:.2f}): Win Rate = {win_rate_low:.2f}% (n={count_low})")
        print(f"  Edge (High - Low): {win_rate_high - win_rate_low:+.2f}%")
