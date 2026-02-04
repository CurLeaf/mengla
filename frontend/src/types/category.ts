export interface CategoryChild {
  catId: number;
  catName?: string;
  catNameCn?: string;
  children?: CategoryChild[];
}

export interface Category {
  catId: number;
  catName?: string;
  catNameCn?: string;
  children?: CategoryChild[];
}

export type CategoryList = Category[];
