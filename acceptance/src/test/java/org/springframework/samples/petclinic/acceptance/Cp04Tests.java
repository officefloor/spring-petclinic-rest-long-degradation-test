package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp04: optional email; if present it must be unique across owners (409). */
@Tag("cp04")
class Cp04Tests extends AcceptanceBase {

	@Test
	void coreRejectsDuplicateEmail() throws Exception {
		String email = uniqueEmail();
		ObjectNode a = ownerNode();
		a.put("email", email);
		createOwnerOk(a);
		ObjectNode b = ownerNode(); // everything else distinct
		b.put("email", email);
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityAllowsMissingEmail() throws Exception {
		createOwnerOk(ownerNode());
		createOwner(ownerNode()).andExpect(status().is2xxSuccessful());
	}

	@Test
	void functionalityStoresEmail() throws Exception {
		String email = uniqueEmail();
		ObjectNode a = ownerNode();
		a.put("email", email);
		int id = createOwnerOk(a);
		getOwner(id).andExpect(jsonPath("$.email").value(email));
	}
}
