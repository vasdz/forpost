function App() {
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-16 text-slate-100">
      <section
        aria-labelledby="legacy-unavailable-title"
        className="mx-auto max-w-2xl rounded-2xl border border-amber-400/40 bg-slate-900 p-8 shadow-2xl"
        role="status"
      >
        <p className="text-sm font-medium uppercase tracking-[0.16em] text-amber-200">Форпост</p>
        <h1 id="legacy-unavailable-title" className="mt-3 text-3xl font-semibold">
          Legacy-клиент выведен из эксплуатации
        </h1>
        <p className="mt-5 text-lg leading-8 text-slate-200">
          Интеграция с реальными данными и обученной моделью пока недоступна.
        </p>
        <p className="mt-4 leading-7 text-slate-400">
          Для работы с локальным обезличенным снимком используйте корневое Next.js-приложение.
          Этот Vite-клиент не показывает прогнозы, отчёты или заявки, сформированные из заглушек.
        </p>
      </section>
    </main>
  );
}

export default App;
