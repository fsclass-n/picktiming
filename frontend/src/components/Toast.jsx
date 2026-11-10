import { createContext, useCallback, useContext, useState } from 'react';

const ToastContext = createContext(() => {});
const STYLE = { success: 'bg-emerald-600', danger: 'bg-rose-600', dark: 'bg-slate-800' };

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const toast = useCallback((message, type = 'dark') => {
    const id = Math.random();
    setItems((xs) => [...xs, { id, message, type }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 3000);
  }, []);
  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="fixed bottom-6 left-1/2 z-[70] flex -translate-x-1/2 flex-col gap-2" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`keep-dark ${STYLE[t.type] || STYLE.dark} rounded-xl px-4 py-3 text-sm text-white shadow-lg`}>{t.message}</div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
