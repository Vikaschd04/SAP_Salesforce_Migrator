import { Component, Input, Output, EventEmitter, OnInit } from '@angular/core';
import { Observable } from 'rxjs';

import { Product } from '../models/product.model';
import { ProductService } from '../services/product.service';
import { CartService } from '../services/cart.service';

/**
 * Product Detail Page (PDP). Loads one product by code, lets the shopper pick a
 * quantity (bounded by stock), and add it to the cart — emitting an event the
 * parent can react to.
 */
@Component({
  selector: 'app-product-detail',
  templateUrl: './product-detail.component.html',
  styleUrls: ['./product-detail.component.scss'],
})
export class ProductDetailComponent implements OnInit {
  @Input() productCode!: string;
  @Output() added = new EventEmitter<Product>();

  product?: Product;
  quantity = 1;
  loading = true;

  constructor(
    private readonly productService: ProductService,
    private readonly cartService: CartService,
  ) {}

  ngOnInit(): void {
    this.productService.getProduct(this.productCode).subscribe((product) => {
      this.product = product;
      this.loading = false;
    });
  }

  /** True when the product exists, is active and has stock. */
  get canAddToCart(): boolean {
    return !!this.product && this.product.active && this.product.stockLevel > 0;
  }

  increaseQuantity(): void {
    if (this.product && this.quantity < this.product.stockLevel) {
      this.quantity += 1;
    }
  }

  decreaseQuantity(): void {
    if (this.quantity > 1) {
      this.quantity -= 1;
    }
  }

  addToCart(): void {
    if (!this.canAddToCart || !this.product) {
      return;
    }
    this.cartService.addItem(this.product, this.quantity);
    this.added.emit(this.product);
  }
}
