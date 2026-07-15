package com.store.customer;

import java.util.List;

/** Customer data access. Customer is a dependency of the Order domain. */
public interface CustomerDao {

    CustomerModel findByUid(String uid);

    List<CustomerModel> findByEmailDomain(String domain);
}
