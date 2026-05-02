"""
Forward-Chaining Inference Engine for Drone Cargo Routing

First-Order Logic tabanlı kural motoru.
GA'nın chromosome decode aşamasında fizibilite kontrolü yapar.

Temel bileşenler:
  - Predicate: Bir önermeyi (proposition) temsil eder. Ör: CanCarry(drone_1, pkg_01, trip_1)
  - Rule: "Eğer şu koşullar sağlanıyorsa → şu sonuç çıkar" yapısı (Modus Ponens)
  - KnowledgeBase: Bilinen gerçekler (facts) + kurallar deposu
  - InferenceEngine: Forward chaining ile yeni gerçekler türetir
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any


# ---------------------------------------------------------------------------
# Predicate — tek bir mantıksal önerme
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Predicate:
    """
    Bir mantıksal önermeyi temsil eder.

    Örnek:
        Predicate("CanCarry", ("drone_1", "pkg_01", "trip_1"))
        Predicate("TimeWindowViolation", ("pkg_03",))

    frozen=True → hash'lenebilir, set içinde tutulabilir.
    Bu önemli çünkü KnowledgeBase facts'leri set olarak tutuyor;
    aynı fact'i iki kez eklememek için hash gerekli.
    """
    name: str
    args: tuple[str, ...] = ()

    def __str__(self) -> str:
        if self.args:
            return f"{self.name}({', '.join(self.args)})"
        return self.name


# ---------------------------------------------------------------------------
# Rule — antecedent → consequent yapısı
# ---------------------------------------------------------------------------

@dataclass
class Rule:
    """
    Bir mantıksal kural: tüm antecedent'ler doğruysa → consequent'ler çıkarılır.

    Klasik Modus Ponens:
        P₁ ∧ P₂ ∧ ... ∧ Pₙ → Q₁ ∧ Q₂ ∧ ... ∧ Qₘ

    Ama bizim kurallarımız (R1-R6) statik fact matching değil,
    runtime'da hesaplama gerektiriyor (ör: "CurrentLoad + Weight ≤ MaxPayload").
    Bu yüzden antecedent olarak callable bir fonksiyon (condition) kullanıyoruz.

    condition: Bir fonksiyon. KnowledgeBase'i parametre alır, bool döner.
               True dönerse → consequent_generator çağrılır.
    consequent_generator: KnowledgeBase'den yeni Predicate'ler üretir.
    """
    name: str
    description: str
    condition: Callable[[KnowledgeBase], bool]
    consequent_generator: Callable[[KnowledgeBase], list[Predicate]]


# ---------------------------------------------------------------------------
# KnowledgeBase — facts + rules deposu
# ---------------------------------------------------------------------------

class KnowledgeBase:
    """
    Bilgi tabanı: bilinen gerçekler (facts) ve kurallar.

    facts → set[Predicate]: Şu anda doğru bildiğimiz önermeler.
    rules → list[Rule]: Uygulanabilecek kurallar.
    context → dict: Kuralların hesaplama yapabilmesi için gerekli
                    runtime verileri (scenario, drone durumu, distance matrix vb.)

    context neden var?
    -----------------
    Pure FOL'da her şey predicate ile ifade edilir. Ama biz gerçek bir
    yazılım yapıyoruz ve "CurrentLoad(drone_1, trip_1) = 3.5" gibi
    sayısal değerleri predicate olarak tutmak yerine, context dict'inde
    doğrudan Python objesi olarak tutuyoruz. Kurallar bu context'e
    erişip hesaplama yapıyor. Bu, FOL'un spirit'ine sadık kalırken
    pratikte verimli bir yaklaşım.
    """

    def __init__(self) -> None:
        self.facts: set[Predicate] = set()
        self.rules: list[Rule] = []
        self.context: dict[str, Any] = {}

    # --- Fact işlemleri ---

    def add_fact(self, predicate: Predicate) -> bool:
        """
        Yeni bir fact ekler. Zaten varsa False döner (değişiklik yok).
        Forward chaining'de "yeni fact eklendi mi?" kontrolü için kullanılır.
        """
        if predicate in self.facts:
            return False
        self.facts.add(predicate)
        return True

    def has_fact(self, name: str, args: tuple[str, ...] = ()) -> bool:
        """Belirli bir fact'in var olup olmadığını kontrol eder."""
        return Predicate(name, args) in self.facts

    def get_facts_by_name(self, name: str) -> list[Predicate]:
        """Belirli bir isimdeki tüm fact'leri döner."""
        return [f for f in self.facts if f.name == name]

    # --- Rule işlemleri ---

    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)

    # --- Context işlemleri ---

    def set_context(self, key: str, value: Any) -> None:
        self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    def clear(self) -> None:
        """Tüm fact'leri ve context'i temizler. Kurallar kalır."""
        self.facts.clear()
        self.context.clear()

    def clear_facts(self) -> None:
        """Sadece fact'leri temizler, context ve kurallar kalır."""
        self.facts.clear()


# ---------------------------------------------------------------------------
# InferenceEngine — Forward Chaining
# ---------------------------------------------------------------------------

class InferenceEngine:
    """
    Forward-chaining inference engine.

    Çalışma prensibi:
    1. Tüm kuralları sırayla kontrol et
    2. Koşulu sağlanan kuralın sonuçlarını (consequent) üret
    3. Yeni fact'ler knowledge base'e ekle
    4. Eğer en az bir yeni fact eklendiyse → 1'e dön
    5. Hiç yeni fact eklenmediyse → dur (saturation)

    max_iterations: Sonsuz döngüye karşı güvenlik. Normalde
    kurallarımız az olduğu için 2-3 iterasyonda saturate olur.
    """

    def __init__(self, kb: KnowledgeBase, max_iterations: int = 50) -> None:
        self.kb = kb
        self.max_iterations = max_iterations
        self.trace: list[dict] = []  # Hangi kural ne üretti — debug + rapor için

    def run(self) -> list[Predicate]:
        """
        Forward chaining çalıştırır.
        Dönen değer: Bu çalışma boyunca eklenen TÜM yeni fact'ler.
        """
        all_new_facts: list[Predicate] = []

        for iteration in range(self.max_iterations):
            new_facts_this_round: list[Predicate] = []

            for rule in self.kb.rules:
                # Modus Ponens: koşul sağlanıyor mu?
                if rule.condition(self.kb):
                    # Consequent'leri üret
                    consequents = rule.consequent_generator(self.kb)
                    for pred in consequents:
                        # Sadece GERÇEKTEN yeni olan fact'leri ekle
                        if self.kb.add_fact(pred):
                            new_facts_this_round.append(pred)
                            self.trace.append({
                                "iteration": iteration,
                                "rule": rule.name,
                                "produced": str(pred),
                            })

            if not new_facts_this_round:
                # Saturation — yeni fact yok, dur
                break

            all_new_facts.extend(new_facts_this_round)

        return all_new_facts

    def get_trace(self) -> list[dict]:
        """Inference trace'i döner — raporda Modus Ponens örneği için kullanılacak."""
        return self.trace

    def reset_trace(self) -> None:
        self.trace.clear()
