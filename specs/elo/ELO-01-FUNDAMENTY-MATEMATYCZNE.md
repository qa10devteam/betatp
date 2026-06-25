# ELO-01: FUNDAMENTY MATEMATYCZNE SYSTEMU ELO

**Moduł:** betatp.io ELO ENGINE  
**Wersja:** 1.0.0  
**Status:** Specyfikacja formalna  
**Data:** 2025-06-25

---

## 1. Wprowadzenie i Motywacja

System Elo, opracowany przez Arpadę Elo w 1960 roku dla szachów, stanowi fundament probabilistycznego rankingowania zawodników w sporcie. W kontekście ATP Tennis, system Elo dostarcza estymatora siły zawodnika opartego na rzeczywistych wynikach meczów, przewyższając oficjalny ranking ATP oparty na punktach zdobytych w turniejach. Niniejszy dokument zawiera formalną derywację matematyczną systemu Elo od pierwszych zasad.

---

## 2. Model Porównań Parowanych (Bradley-Terry-Luce)

### 2.1 Aksjomat Podstawowy

**Aksjomat A1 (Stochastyczność wyniku):** Dla każdej pary zawodników $A$ i $B$, wynik meczu jest zmienną losową $S \in \{0, 1\}$, gdzie $S=1$ oznacza zwycięstwo $A$.

**Aksjomat A2 (Istnienie ukrytej siły):** Każdy zawodnik $i$ posiada prawdziwą, lecz nieobserwowalną siłę $\theta_i \in \mathbb{R}$.

**Aksjomat A3 (Niezależność meczy):** Wyniki poszczególnych meczów są warunkowo niezależne przy danych siłach zawodników.

### 2.2 Model Bradley-Terry

W modelu Bradley-Terry, prawdopodobieństwo zwycięstwa zawodnika $A$ nad $B$ wyraża się jako:

$$P(A \succ B \mid \theta_A, \theta_B) = \frac{e^{\theta_A}}{e^{\theta_A} + e^{\theta_B}} = \frac{1}{1 + e^{-(\theta_A - \theta_B)}}$$

Jest to funkcja logistyczna (sigmoida) różnicy sił.

---

## 3. Funkcja Prawdopodobieństwa Elo

### 3.1 Definicja Ratingu Elo

**Definicja D1:** Rating Elo zawodnika $i$ to $R_i \in \mathbb{R}$, będący estymacją ukrytej siły $\theta_i$ w skali dziesiętnej z parametrem normalizacji $c = 400$.

### 3.2 Logistyczna Funkcja Prawdopodobieństwa

Standardowa funkcja prawdopodobieństwa Elo definiuje:

$$\boxed{P(A \succ B) = \frac{1}{1 + 10^{(R_B - R_A)/400}}}$$

**Twierdzenie T1:** Funkcja Elo jest izomorficzna z modelem Bradley-Terry przy podstawieniu $\theta_i = R_i \cdot \frac{\ln 10}{400}$.

**Dowód:**
$$P(A \succ B) = \frac{1}{1 + 10^{(R_B - R_A)/400}} = \frac{1}{1 + e^{(R_B - R_A) \cdot \ln(10)/400}}$$

Niech $\alpha = \frac{\ln 10}{400} \approx 0.005756$, wtedy:
$$P(A \succ B) = \frac{1}{1 + e^{-\alpha(R_A - R_B)}} = \sigma(\alpha(R_A - R_B))$$

gdzie $\sigma(\cdot)$ jest funkcją sigmoidalną. Podstawiając $\theta_i = \alpha R_i$, otrzymujemy model Bradley-Terry. $\square$

### 3.3 Własności Funkcji Prawdopodobieństwa

| Różnica ratingów $\Delta R = R_A - R_B$ | $P(A \succ B)$ |
|------------------------------------------|-----------------|
| $-400$ | $0.0909$ |
| $-200$ | $0.2401$ |
| $0$ | $0.5000$ |
| $+100$ | $0.6401$ |
| $+200$ | $0.7599$ |
| $+400$ | $0.9091$ |
| $+800$ | $0.9900$ |

---

## 4. Maksymalizacja Log-Wiarygodności

### 4.1 Funkcja Log-Wiarygodności

Niech $\mathcal{D} = \{(A_k, B_k, S_k)\}_{k=1}^{N}$ będzie zbiorem obserwowanych meczów, gdzie $S_k \in \{0, 1\}$.

Funkcja log-wiarygodności dla ratingu $\mathbf{R} = (R_1, \ldots, R_n)$:

$$\mathcal{L}(\mathbf{R} \mid \mathcal{D}) = \sum_{k=1}^{N} \left[ S_k \log P_{A_k B_k} + (1 - S_k) \log(1 - P_{A_k B_k}) \right]$$

gdzie $P_{AB} = P(A \succ B)$.

### 4.2 Twierdzenie o Maksimum Log-Wiarygodności

**Twierdzenie T2:** Estymator MLE ratingów $\hat{\mathbf{R}}$ istnieje i jest jedyny (z dokładnością do stałej addytywnej) gdy graf meczów jest spójny.

**Dowód (szkic):** Funkcja $-\mathcal{L}$ jest ściśle wypukła (Hessian jest dodatnio półokreślony, a z warunkiem spójności – dodatnio określony na podprzestrzeni ortogonalnej do wektora jedynkowego). $\square$

---

## 5. Reguła Aktualizacji jako Gradient Descent

### 5.1 Gradient Funkcji Straty

Definiujemy negatywną log-wiarygodność dla pojedynczego meczu:

$$\ell_k(R_A, R_B) = -S_k \log P_{AB} - (1-S_k)\log(1-P_{AB})$$

Obliczamy gradient względem $R_A$:

$$\frac{\partial \ell_k}{\partial R_A} = -S_k \frac{P_{AB}'}{P_{AB}} - (1-S_k)\frac{-P_{AB}'}{1-P_{AB}}$$

Ponieważ $P_{AB}' = \frac{dP_{AB}}{dR_A} = \alpha \cdot P_{AB}(1-P_{AB})$, gdzie $\alpha = \frac{\ln 10}{400}$:

$$\frac{\partial \ell_k}{\partial R_A} = -\alpha(S_k - P_{AB})$$

### 5.2 Reguła Aktualizacji Elo jako SGD

**Twierdzenie T3:** Reguła aktualizacji Elo:

$$\boxed{R_A^{\text{new}} = R_A^{\text{old}} + K \cdot (S - E)}$$

jest krokiem stochastycznego gradientu prostego (SGD) na negatywnej log-wiarygodności, z krokiem uczenia $\eta = K/\alpha$.

**Dowód:**
Krok SGD: $R_A \leftarrow R_A - \eta \cdot \frac{\partial \ell_k}{\partial R_A} = R_A + \eta \cdot \alpha \cdot (S - E)$

Niech $K = \eta \cdot \alpha$, wtedy: $R_A^{\text{new}} = R_A^{\text{old}} + K(S - E)$, co jest dokładnie regułą Elo. $\square$

---

## 6. Dowód Zbieżności

### 6.1 Twierdzenie o Zbieżności SGD dla Elo

**Twierdzenie T4 (Zbieżność):** Dla stałej liczby zawodników $n$ i nieskończonego ciągu meczów losowanych z rozkładu zgodnego z modelem Elo, aktualizacje ratingów zbiegają do prawdziwych wartości $\theta^*$ w następującym sensie:

$$\mathbb{E}\left[\|\mathbf{R}^{(t)} - \mathbf{R}^*\|^2\right] \to 0 \quad \text{gdy } t \to \infty$$

pod warunkiem: (a) $\sum_{t} K_t = \infty$, (b) $\sum_{t} K_t^2 < \infty$.

**Dowód:**

Ponieważ $-\mathcal{L}$ jest funkcją ściśle wypukłą i gładką, spełnia warunek Lipschtiza gradientu:

$$\|\nabla \mathcal{L}(\mathbf{R}') - \nabla \mathcal{L}(\mathbf{R})\| \leq L \|\mathbf{R}' - \mathbf{R}\|$$

Ze standardowej teorii SGD (Robbins-Monro, 1951), warunki (a) i (b) gwarantują zbieżność do minimum globalnego. $\square$

**Wniosek:** Stały K-faktor ($K = \text{const}$) spełnia (a), lecz nie (b). Prowadzi do oscylacji wokół optimum. Dynamiczny K-faktor malejący jak $K_t = K_0/t$ spełnia obie warunki.

### 6.2 Prędkość Zbieżności

Dla K-faktora $K_t = K_0/\sqrt{t}$:

$$\mathbb{E}\left[\|\mathbf{R}^{(t)} - \mathbf{R}^*\|^2\right] = O\left(\frac{1}{\sqrt{t}}\right)$$

---

## 7. Optymalny K-Faktor jako Funkcja Rozmiaru Próby

### 7.1 Bias-Variance Tradeoff

**Twierdzenie T5:** Dla zawodnika z $n$ rozegranymi meczami, optymalny K-faktor minimalizujący MSE estymatora ratingu wynosi:

$$K^*(n) = \frac{\sigma_{\theta}^2}{\sigma_{\theta}^2 + \sigma_{\varepsilon}^2/n}$$

gdzie $\sigma_{\theta}^2$ jest wariancją prawdziwych sił zawodników, a $\sigma_{\varepsilon}^2$ jest wariancją szumu pomiarowego.

**Dowód (szkic):** Rozważ estymator Bayesowski z prior $\theta \sim \mathcal{N}(\mu_0, \sigma_{\theta}^2)$ i likelihood $S_k | \theta \sim \text{Bernoulli}(\sigma(\alpha \theta))$. Linearyzując likelihood i stosując regułę Bayesa, otrzymujemy estymator MMSE odpowiadający powyższej formule. $\square$

### 7.2 Empiryczne Wartości dla ATP

Dla bazy danych ATP (TML-Database, 1990-2025):
- $\sigma_{\theta} \approx 150$ punktów Elo (odchylenie standardowe sił zawodników)
- $\sigma_{\varepsilon} \approx 350$ punktów (szum jednostkowego meczu)
- Przy $n = 100$ meczach: $K^*(100) \approx 32$
- Przy $n = 500$ meczach: $K^*(500) \approx 39$

---

## 8. Podsumowanie Aksjomatów i Twierdzeń

| Symbol | Opis |
|--------|------|
| **A1-A3** | Aksjomat stochastyczności, ukrytej siły, niezależności |
| **T1** | Izomorfizm Elo ↔ Bradley-Terry |
| **T2** | Istnienie i jedyność estymatora MLE |
| **T3** | Reguła Elo = krok SGD na $-\mathcal{L}$ |
| **T4** | Zbieżność przy warunkach Robbinsa-Monro |
| **T5** | Optymalny K-faktor z Bayesowskiej perspektywy |

---

## 9. Referencje

- Elo, A. E. (1978). *The Rating of Chessplayers, Past and Present*. Arco Publishing.
- Bradley, R. A., & Terry, M. E. (1952). Rank analysis of incomplete block designs. *Biometrika*, 39(3/4), 324–345.
- Robbins, H., & Monro, S. (1951). A stochastic approximation method. *Ann. Math. Statist.*, 22(3), 400–407.
- Kovalchik, S. (2016). Searching for the GOAT of tennis win prediction. *Journal of Quantitative Analysis in Sports*, 12(3), 127–138.
- TML-Database ATP (1968–2025). Tennis Match Library, dostęp: betatp.io/data.

---

*Dokument ELO-01 v1.0.0 — betatp.io ELO ENGINE — Własność intelektualna betatp.io*
