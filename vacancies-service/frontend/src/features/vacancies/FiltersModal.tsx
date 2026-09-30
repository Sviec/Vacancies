import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { FilterPanel } from "@/features/vacancies/FilterPanel";
import type { FilterChange } from "@/features/vacancies/FilterPanel";
import type { FeedFilters } from "@/features/vacancies/feed-state";

interface FiltersModalProps {
  open: boolean;
  onClose: () => void;
  filters: FeedFilters;
  onChange: FilterChange;
  onReset: () => void;
  total: number | null;
}

/**
 * Фильтры ниже 768px: та же панель в модальном окне. Изменения применяются
 * сразу, «Готово» только закрывает окно.
 * TODO: модалка — ниже 768px; от 768px фильтры в сворачиваемой колонке.
 */
export function FiltersModal({ open, onClose, filters, onChange, onReset, total }: FiltersModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Фильтры"
      description={total === null ? "Изменения применяются сразу." : `Изменения применяются сразу · найдено ${total}`}
      footer={
        <Button variant="primary" onClick={onClose}>
          Готово
        </Button>
      }
    >
      <FilterPanel filters={filters} onChange={onChange} onReset={onReset} />
    </Modal>
  );
}
