package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp14: reject creating an owner once their city already contains 8 owners. */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreRejectsOverCityCap() throws Exception {
		String city = "Capville" + seq(); // fresh city, no existing owners
		for (int i = 0; i < 8; i++) {
			ObjectNode o = ownerNode();
			o.put("city", city);
			createOwnerOk(o);
		}
		ObjectNode ninth = ownerNode();
		ninth.put("city", city);
		createOwner(ninth).andExpect(status().isBadRequest());
	}
}
