import { Component, OnInit } from '@angular/core';
import { Observable } from 'rxjs';

import { Product } from '../models/product.model';
import { ProductService } from '../services/product.service';
import { CartService } from '../services/cart.service';

/**
 * Product Listing Page (PLP). Loads the catalogue, supports a text filter and a
 * sort, and lets the shopper add a product straight to the cart.
 */
@Component({
  selector: 'app-product-list',
  templateUrl: './product-list.component.html',
  styleUrls: ['./product-list.component.scss'],
})
export class ProductListComponent implements OnInit {
  products: Product[] = [];
  filtered: Product[] = [];
  query = '';
  sortBy: 'name' | 'price' = 'name';
  loading = true;

  constructor(
    private readonly productService: ProductService,
    private readonly cartService: CartService,
  ) {}

  ngOnInit(): void {
    this.productService.getProducts().subscribe((products) => {
      this.products = products;
      this.applyFilter();
      this.loading = false;
    });
  }

  /** Re-derive the visible list from the query + sort. */
  applyFilter(): void {
    const term = this.query.trim().toLowerCase();
    const list = term
      ? this.products.filter(
          (p) =>
            p.name.toLowerCase().includes(term) ||
            p.description.toLowerCase().includes(term),
        )
      : [...this.products];

    list.sort((a, b) =>
      this.sortBy === 'price' ? a.price - b.price : a.name.localeCompare(b.name),
    );
    this.filtered = list;
  }

  onSearch(term: string): void {
    this.query = term;
    this.applyFilter();
  }

  changeSort(sortBy: 'name' | 'price'): void {
    this.sortBy = sortBy;
    this.applyFilter();
  }

  addToCart(product: Product): void {
    if (product.stockLevel > 0) {
      this.cartService.addItem(product, 1);
    }
  }

  trackByCode(_index: number, product: Product): string {
    return product.code;
  }
}
