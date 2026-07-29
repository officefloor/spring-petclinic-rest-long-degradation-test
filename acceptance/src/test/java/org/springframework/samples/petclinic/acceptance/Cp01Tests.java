package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp01: reject creating an owner identical to an existing one (409). */
@Tag("cp01")
class Cp01Tests extends AcceptanceBase {

	@Test
	void coreRejectsIdenticalOwner() throws Exception {
		ObjectNode o = ownerNode();
		createOwnerOk(o);
		createOwner(o).andExpect(status().isConflict()); // byte-identical -> 409
	}

	@Test
	void functionalityAllowsTwoDistinctOwners() throws Exception {
		createOwnerOk(ownerNode());
		createOwner(ownerNode()).andExpect(status().is2xxSuccessful());
	}
}
