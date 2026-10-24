const form = document.getElementById("booking-form");

if (form) {
  const dateInput = form.querySelector('input[name="date"]');

  // Выбор слота: крупно показываем выбранное время и включаем кнопку.
  form.addEventListener("change", (event) => {
    const slot = event.target;
    if (!(slot instanceof HTMLInputElement) || slot.name !== "start") return;

    const summary = document.getElementById("booking-summary");
    const submit = document.getElementById("booking-submit");
    const [year, month, day] = dateInput.value.split("-");
    const range = `${slot.value}–${slot.dataset.end}`;

    if (summary) {
      summary.textContent = `${day}.${month}.${year}, ${range}`;
      summary.classList.remove("text-muted");
      summary.classList.add("text-lime");
    }
    if (submit) {
      submit.disabled = false;
      submit.textContent = `Забронировать ${range}`;
    }
  });

  // Защита от двойной отправки.
  form.addEventListener("submit", () => {
    const submit = document.getElementById("booking-submit");
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Бронируем…";
    }
  });
}