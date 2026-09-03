interface Service {
  fetch<T>(id: T): Promise<T>;
}

declare function ambient(value: string): void;

export function identity<T>(value: T): T {
  return value;
}

const select = <T,>(value: T): T => {
  return value;
};

type Props<T> = { items: T[] };
export const List = <T,>({ items }: Props<T>) => (
  <ul>
    {items.map((item) => <li key={String(item)}>{String(item)}</li>)}
  </ul>
);

abstract class Repository<T> {
  get<U>(value: U): U {
    return value;
  }

  abstract save(value: T): void;
}

function parse(value: string): string;
function parse(value: number): number;
function parse(value: string | number) {
  return value;
}
