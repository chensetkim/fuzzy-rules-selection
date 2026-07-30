# Multi Input Fuzzy Logic System Face Challenge


Multi-input fuzzy logic systems is the exponential explosion of rules, computational complexity, and difficulty in tuning membership functions.

- **Exponential Complexity**: If a system has n inputs and each input has m membership functions, the total number of required rules is \(m^{n}\). Adding a single new input dramatically multiplies the processing overhead.
- **Design Difficulties**: Manually formulating, verifying, and tuning thousands of IF-THEN rules based on human expert knowledge becomes unrealistic.
- **High Memory Usage**: Storing vast multidimensional rule tables requires massive amounts of hardware memory.
- **Slow Inference Speeds**: Processing huge rule bases significantly slows down execution, making real-time control highly unstable or sluggish.
- **Conflicting Rules**: Managing multiple interacting objectives increases the likelihood of human error, leading to contradictory logic paths.

We have fuzzy intrusion detection system that has seven inputs variables.

Flat fuzzy number of rules = 3^7 = 2187 rules  (~ 17kb)

Challenge with IoT devices = small memory, computing power, battery life

Two methods CARS & T-HFIS for fuzzy rules selection based accuracy, memory, flash constraint.
