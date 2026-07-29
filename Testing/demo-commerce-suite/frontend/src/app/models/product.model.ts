/** Domain model for a catalogue product (mirrors the Hybris Product item type). */
export interface Product {
  code: string;
  name: string;
  description: string;
  price: number;
  currency: string;
  stockLevel: number;
  productType: 'PHYSICAL' | 'DIGITAL';
  imageUrl?: string;
  active: boolean;
}

/** A single line in the cart. */
export interface CartItem {
  product: Product;
  quantity: number;
}
