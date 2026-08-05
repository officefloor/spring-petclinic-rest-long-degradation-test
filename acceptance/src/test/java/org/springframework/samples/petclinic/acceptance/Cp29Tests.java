package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp29 postcode: a 4-digit 'postcode' valid for the owner's city is stored and returned; a
 *  malformed postcode is rejected (400). Postcode is validated WHEN PRESENT but optional when
 *  absent, so every earlier requirement's minimal owner (which sends no postcode) stays valid at
 *  this and all later checkpoints -- the operative request contract stays backward-compatible. */
@Tag("cp29")
class Cp29Tests extends AcceptanceBase {

	@Test
	void coreStoresValidPostcode() throws Exception {
		int id = createOwnerOk(withPostcode(ownerNode()));
		getOwner(id).andExpect(jsonPath("$.postcode").value("2000"));
	}

	@Test
	void coreAcceptsOwnerWithoutPostcode() throws Exception {
		createOwner(ownerNode()).andExpect(status().is2xxSuccessful());
	}

	@Test
	void errorRejectsMalformedPostcode() throws Exception {
		ObjectNode o = ownerNode();
		o.put("postcode", "12");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
