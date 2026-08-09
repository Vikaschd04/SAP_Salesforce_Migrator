package com.acme.core.service.impl;

import de.hybris.bootstrap.annotations.UnitTest;

import com.acme.core.enums.FulfilmentState;

import org.junit.Before;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

/**
 * The fulfilment state machine. These transitions are contractual — a warehouse
 * integration depends on them.
 */
@UnitTest
public class DefaultOrderFulfilmentServiceTest
{
	private DefaultOrderFulfilmentService service;

	@Before
	public void setUp()
	{
		service = new DefaultOrderFulfilmentService();
	}

	@Test
	public void pendingMayAdvanceToAllocated()
	{
		assertTrue(service.isForwardTransition(FulfilmentState.PENDING, FulfilmentState.ALLOCATED));
	}

	@Test
	public void allocatedMayAdvanceToPicked()
	{
		assertTrue(service.isForwardTransition(FulfilmentState.ALLOCATED, FulfilmentState.PICKED));
	}

	@Test
	public void pickedMayAdvanceToShipped()
	{
		assertTrue(service.isForwardTransition(FulfilmentState.PICKED, FulfilmentState.SHIPPED));
	}

	@Test
	public void statesMayNotBeSkipped()
	{
		assertFalse(service.isForwardTransition(FulfilmentState.PENDING, FulfilmentState.SHIPPED));
	}

	@Test
	public void fulfilmentNeverRunsBackwards()
	{
		assertFalse(service.isForwardTransition(FulfilmentState.SHIPPED, FulfilmentState.PICKED));
	}

	@Test
	public void deliveredIsTheTerminalState()
	{
		assertEquals(4, service.order(FulfilmentState.DELIVERED));
	}
}
