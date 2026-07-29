import { Component, Output, EventEmitter, OnInit } from '@angular/core';

import { CartItem } from '../models/product.model';
import { CartService } from '../services/cart.service';

/**
 * Cart summary. Shows the line items, the running total, lets the shopper remove
 * a line, and emits a checkout event carrying the current total.
 */
@Component({
  selector: 'app-cart',
  templateUrl: './cart.component.html',
  styleUrls: ['./cart.component.scss'],
})
export class CartComponent implements OnInit {
  @Output() checkout = new EventEmitter<number>();

  items: CartItem[] = [];

  constructor(private readonly cartService: CartService) {}

  ngOnInit(): void {
    this.cartService.getItems().subscribe((items) => (this.items = items));
  }

  /** The running cart total. */
  get total(): number {
    return this.cartService.getTotal();
  }

  get isEmpty(): boolean {
    return this.items.length === 0;
  }

  lineTotal(item: CartItem): number {
    return item.product.price * item.quantity;
  }

  remove(productCode: string): void {
    this.cartService.removeItem(productCode);
  }

  onCheckout(): void {
    if (!this.isEmpty) {
      this.checkout.emit(this.total);
    }
  }
}
